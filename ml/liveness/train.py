"""Fine-tune AASIST on our preprocessed clips, starting from a public checkpoint.

From ml/liveness/, after preprocess.py:

    python train.py --init <weights.pth> --name first-try
    python train.py --init <weights.pth> --name smoke --epochs 1 --steps 20 --dev-per-group 20
    python train.py --name first-try --resume     # carry on after a stop

--data-dir can also be a pack made by kaggle_pack.py, for training on Kaggle.

Each epoch is --steps batches drawn by training_data.balanced_sampler, then a
score on a fixed sample of the dev split. Training never sees dev or test.

Writes, in data/runs/<name>/:
- best.pth: the weights with the best dev score. score_baseline.py reads it
  like a public checkpoint: --model ours=data/runs/<name>/best.pth
- last.pth: everything needed to carry on (weights, optimizer, epoch).
- log.csv: loss and dev EER by epoch; settings.json: how it was run.

The dev score is the mean of each dataset's EER, so each dataset counts the
same whatever its size.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader

from augment import Augmenter
from models.aasist import Model
from score_baseline import MODEL_CONFIG, eer
from training_data import REAL, ClipDataset, balanced_sampler, even_sample, load_split
from validate import DEFAULT_DATA_DIR

NOISE_DIR = "augment/RIRS_NOISES"


def evaluate(model: torch.nn.Module, loader: DataLoader, clips: pd.DataFrame, device: str) -> dict:
    """EER on the dev sample: each dataset's, and their mean."""
    model.eval()
    scores = []
    with torch.inference_mode():
        for x, _ in loader:
            scores.append(model(x.to(device))[1][:, REAL].float().cpu().numpy())
    clips = clips.assign(score=np.concatenate(scores))
    result = {}
    for source, g in clips.groupby("source"):
        real = g.loc[g["label"] == "bonafide", "score"].to_numpy()
        fake = g.loc[g["label"] == "spoof", "score"].to_numpy()
        if len(real) and len(fake):
            result[f"eer_{source}"] = 100 * eer(real, fake)[0]
    result["dev_eer"] = float(np.mean(list(result.values())))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", required=True, help="folder under data/runs/")
    parser.add_argument("--init", type=Path, help="checkpoint to start from")
    parser.add_argument("--resume", action="store_true", help="carry on from data/runs/<name>/last.pth")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--steps", type=int, default=2000, help="batches per epoch")
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--lr", type=float, default=3e-5)
    parser.add_argument("--dev-per-group", type=int, default=500, help="dev clips per dataset and label")
    parser.add_argument("--workers", type=int, default=8, help="DataLoader processes")
    parser.add_argument("--noise-dir", type=Path, help=f"default: <data-dir>/{NOISE_DIR}")
    parser.add_argument("--no-noise", action="store_true", help="skip reverb and noise (codecs still apply)")
    parser.add_argument("--out-dir", type=Path, help="where runs go; default: <data-dir>/runs")
    parser.add_argument("--max-hours", type=float, help="stop after the last epoch that fits in this time")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    began = time.time()

    run = (args.out_dir or args.data_dir / "runs") / args.name
    last = run / "last.pth"
    if args.resume and not last.exists():
        sys.exit(f"nothing to resume: {last} not found")
    if not args.resume and run.exists():
        sys.exit(f"{run} exists; pick another --name, or add --resume")
    if not args.resume and args.init is None:
        sys.exit("give --init <checkpoint> (training from scratch isn't supported)")
    run.mkdir(parents=True, exist_ok=True)

    torch.manual_seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = Model(MODEL_CONFIG).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, args.epochs * args.steps, eta_min=args.lr / 30)
    start_epoch, best = 1, float("inf")
    if args.resume:
        state = torch.load(last, map_location=device, weights_only=True)
        model.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        scheduler.load_state_dict(state["scheduler"])
        start_epoch, best = state["epoch"] + 1, state["best"]
        print(f"resuming after epoch {state['epoch']} (best dev EER {best:.2f}%)")
    else:
        model.load_state_dict(torch.load(args.init, map_location=device, weights_only=True))
        (run / "settings.json").write_text(json.dumps({k: str(v) for k, v in vars(args).items()}, indent=2))

    train = load_split(args.data_dir, "train")
    dev = even_sample(load_split(args.data_dir, "dev"), args.dev_per_group)
    augment = Augmenter(None if args.no_noise else args.noise_dir or args.data_dir / NOISE_DIR)
    print(f"{device}; {len(train)} train clips; {len(dev)} dev clips; "
          f"{len(augment.rirs)} room echoes, {len(augment.noises)} noises")
    dev_loader = DataLoader(ClipDataset(dev, args.data_dir), batch_size=args.batch, num_workers=args.workers)
    loss_fn = torch.nn.CrossEntropyLoss()

    for epoch in range(start_epoch, args.epochs + 1):
        sampler = balanced_sampler(train, args.steps * args.batch, seed=args.seed * 1000 + epoch)
        loader = DataLoader(ClipDataset(train, args.data_dir, augment), batch_size=args.batch,
                            sampler=sampler, num_workers=args.workers, pin_memory=device == "cuda",
                            drop_last=True)
        model.train()
        started, total = time.time(), 0.0
        for step, (x, y) in enumerate(loader, start=1):
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            loss = loss_fn(model(x, Freq_aug=True)[1], y)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            scheduler.step()
            total += loss.item()
            if step % 100 == 0 or step == args.steps:
                rate = step * args.batch / (time.time() - started)
                print(f"epoch {epoch} step {step}/{args.steps}: loss {total / step:.4f}, {rate:.0f} clips/s",
                      flush=True)

        result = {"epoch": epoch, "loss": total / args.steps, "minutes": (time.time() - started) / 60}
        result |= evaluate(model, dev_loader, dev, device)
        print("  " + ", ".join(f"{k} {v:.2f}" for k, v in result.items() if k != "epoch"), flush=True)
        log = run / "log.csv"
        pd.DataFrame([result]).to_csv(log, mode="a", header=not log.exists(), index=False)
        if result["dev_eer"] < best:
            best = result["dev_eer"]
            torch.save(model.state_dict(), run / "best.pth")
            print(f"  new best: {best:.2f}%")
        # Saved last, and under a temporary name first, so a stop mid-save
        # can't leave a broken last.pth.
        state = {"model": model.state_dict(), "optimizer": optimizer.state_dict(),
                 "scheduler": scheduler.state_dict(), "epoch": epoch, "best": best}
        torch.save(state, run / "last.partial")
        (run / "last.partial").replace(last)

        hours_left = (args.max_hours or float("inf")) - (time.time() - began) / 3600
        if epoch < args.epochs and hours_left < 1.2 * (time.time() - started) / 3600:
            print(f"stopping after epoch {epoch}: another wouldn't fit in --max-hours; carry on with --resume")
            break

    print(f"done; best dev EER {best:.2f}%, weights in {run / 'best.pth'}")


if __name__ == "__main__":
    main()
