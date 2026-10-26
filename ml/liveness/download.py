"""Download the Hugging Face datasets into data/raw/<source>/.

From ml/liveness/:

    python download.py asvspoof5            # dev + 1 of the 10 eval parts (~29 GB)
    python download.py asvspoof5 --eval-parts 3
    python download.py asvspoof5 --train    # adds train (~37 GB), for fine-tuning
    python download.py codecfake            # 1 shard per codec, 16 shards (~10 GB)
    python download.py deepfake_eval_2024   # all of the audio (~4 GB)

Each takes a manageable slice instead of the whole dataset (several are over
100 GB); the options above take more. Downloads resume where they stopped,
and a dropped connection is retried, so it's safe to run a command again.

Deepfake-Eval-2024 is gated: first open its page on huggingface.co while
logged in and request access (it's approved by hand, which can take a
while), then run `huggingface-cli login` once with a read token from
https://huggingface.co/settings/tokens.

The datasets other than ASVspoof 5 and CodecFake come with their own terms,
listed in each loader in sources/.
"""

import argparse
import csv
import hashlib
import sys
import tarfile
import time
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import HfFileSystem, hf_hub_download
from huggingface_hub.utils import GatedRepoError, RepositoryNotFoundError

DEFAULT_DATA_DIR = Path(__file__).parent / "data"
ATTEMPTS = 20  # home connections drop; each retry resumes the partial file


def fetch(repo: str, filename: str, out: Path) -> Path:
    """Download one file into out/, retrying and resuming if the connection drops."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return Path(hf_hub_download(repo, filename, repo_type="dataset", local_dir=out))
        except (GatedRepoError, RepositoryNotFoundError):
            sys.exit(
                f"No access to {repo}. Accept its terms at https://huggingface.co/datasets/{repo} "
                "and run `huggingface-cli login`, then try again."
            )
        except Exception as error:  # network errors come in many types
            if attempt == ATTEMPTS:
                raise
            wait = min(60, 2 ** attempt)
            print(f"  {filename}: {type(error).__name__}; retrying in {wait}s ({attempt}/{ATTEMPTS})")
            time.sleep(wait)


def md5(path: Path) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asvspoof5(out: Path, eval_parts: int, train: bool) -> None:
    """The protocols, all of dev, the first eval_parts of the 10 eval tars,
    and train (37 GB) only if asked for, since it's only needed to fine-tune."""
    repo = "jungjee/asvspoof5"
    # From the dataset's README.txt.
    tars = {
        "flac_T_aa.tar": "b0cc86b14826a7701b52aad4f53daf9c",
        "flac_T_ab.tar": "d05be3f4be7a343fdbdd0ed29fdff2e1",
        "flac_T_ac.tar": "70d1ba4ad75a20aef3dae541fbd321e3",
        "flac_T_ad.tar": "c9bb56af2cc410d98338d74babcb95c9",
        "flac_T_ae.tar": "a3969816982f3e52300d6147ad796df7",
        "flac_D_aa.tar": "df0be44957623991028cce59792beb17",
        "flac_D_ab.tar": "1e8cd685d89b64502692f1bcf1a13db3",
        "flac_D_ac.tar": "5e0031f08c30e4bdbf0c59f91b2d662b",
        "flac_E_aa.tar": "a8c800766f3d4ef87971e2b4f29663e2",
        "flac_E_ab.tar": "c35064188f54f07c87aba58de22534a0",
        "flac_E_ac.tar": "ed7cbcd1b2847998b72472ddf6b445e3",
        "flac_E_ad.tar": "626a080e994b05df49c577d7b3dede8d",
        "flac_E_ae.tar": "05f19a5e64fa556714ae1b38eb2ea70b",
        "flac_E_af.tar": "2ca2f52a3bbf827f7ec155ecb47e85d6",
        "flac_E_ag.tar": "671200b5de2fc1e74a563b07b057af8f",
        "flac_E_ah.tar": "eaf885b1299a61eb07f71e82e96dba37",
        "flac_E_ai.tar": "b2625683bf440abae2af901a45542ad9",
        "flac_E_aj.tar": "c50281c8233af6f3b0899604d21ade44",
    }
    wanted = [t for t in tars if t.startswith("flac_D")]
    wanted += [t for t in tars if t.startswith("flac_E")][:eval_parts]
    if train:
        wanted += [t for t in tars if t.startswith("flac_T")]

    for name in ["README.txt", "LICENSE.txt", "ASVspoof5_protocols.tar"]:
        fetch(repo, name, out)
    with tarfile.open(out / "ASVspoof5_protocols.tar") as t:
        t.extractall(out, filter="data")

    done = out / "extracted.txt"  # tars already unpacked, so a rerun skips them
    finished = set(done.read_text().split()) if done.exists() else set()
    for name in wanted:
        if name in finished:
            continue
        path = fetch(repo, name, out)
        if md5(path) != tars[name]:
            sys.exit(f"{name} is corrupt (md5 mismatch); delete {path} and run again")
        with tarfile.open(path) as t:
            t.extractall(out, filter="data")
        path.unlink()  # the audio is unpacked; the tar would double the space used
        with open(done, "a") as f:
            f.write(name + "\n")
        print(f"unpacked {name}")


def codecfake(out: Path) -> None:
    """One shard from each codec's block, plus one of genuine speech.

    The dataset is 161 Parquet shards sorted by codec, about 10 shards per
    codec. Each shard's audio is written out as WAV files with a
    metadata.csv, so the loader reads it like any other dataset.
    """
    repo = "rogertseng/CodecFake"
    total = 161
    # The middle shard of each block holds a single codec.
    shards = [k * 10 + 5 for k in range(16)]
    meta = out / "metadata.csv"
    seen = set()
    if meta.exists():
        with open(meta, newline="") as f:
            seen = {row["shard"] for row in csv.DictReader(f)}
    else:
        out.mkdir(parents=True, exist_ok=True)
        with open(meta, "w", newline="") as f:
            csv.writer(f).writerow(["file", "label", "speaker_id", "codec", "shard"])

    for k in shards:
        name = f"data/train-{k:05d}-of-{total:05d}.parquet"
        if name in seen:
            continue
        path = fetch(repo, name, out)
        table = pq.read_table(path)
        rows = []
        for record in table.to_pylist():
            codec = record["codec_name"]
            file = Path("audio") / codec / Path(record["audio"]["path"]).name
            (out / file).parent.mkdir(parents=True, exist_ok=True)
            (out / file).write_bytes(record["audio"]["bytes"])
            rows.append([file.as_posix(), record["label"], record["speaker_id"], codec, name])
        with open(meta, "a", newline="") as f:
            csv.writer(f).writerows(rows)
        path.unlink()
        print(f"unpacked {name}: {len(rows)} clips of {rows[0][3]}")


def deepfake_eval_2024(out: Path) -> None:
    repo = "nuriachandra/Deepfake-Eval-2024"
    for name in ["README.md", "audio-metadata-publish.csv"]:
        fetch(repo, name, out)
    fs = HfFileSystem()
    files = fs.ls(f"datasets/{repo}/audio-data", detail=False)
    for n, path in enumerate(sorted(files), start=1):
        relative = path.split(f"datasets/{repo}/", 1)[1]
        if not (out / relative).exists():
            fetch(repo, relative, out)
        if n % 200 == 0:
            print(f"{n}/{len(files)} clips")
    print(f"{len(files)} clips")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", choices=["asvspoof5", "codecfake", "deepfake_eval_2024"])
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--eval-parts", type=int, default=1, help="asvspoof5: eval tars, 1-10")
    parser.add_argument("--train", action="store_true", help="asvspoof5: also the train set (37 GB)")
    args = parser.parse_args()

    out = args.data_dir / "raw" / args.source
    if args.source == "asvspoof5":
        asvspoof5(out, args.eval_parts, args.train)
    elif args.source == "codecfake":
        codecfake(out)
    else:
        deepfake_eval_2024(out)
    print("done")


if __name__ == "__main__":
    main()
