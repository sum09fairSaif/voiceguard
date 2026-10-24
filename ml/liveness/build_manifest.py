"""Build the manifest: run each dataset's loader, then describe every file.

From ml/liveness/, with the datasets unzipped under data/raw/<source>/
(each loader's docstring says where to download it and how to unzip it):

    python build_manifest.py                       # every source that's present
    python build_manifest.py asvspoof2019_la team  # just these

Writes data/manifest.parquet. Nothing here changes or copies the audio.
Run validate.py next to find broken, duplicate or suspicious clips.
"""

import argparse
import hashlib
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import soundfile as sf

import manifest
from sources import LOADERS

DEFAULT_DATA_DIR = Path(__file__).parent / "data"


def describe(path: Path) -> dict:
    """Read a file's header and hash it. Missing or unreadable files get
    blanks here; validate.py reports them."""
    try:
        info = sf.info(str(path))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, RuntimeError, sf.LibsndfileError):
        return {"duration_s": float("nan"), "sample_rate": 0, "channels": 0, "format": "", "sha256": ""}
    return {
        "duration_s": info.frames / info.samplerate,
        "sample_rate": info.samplerate,
        "channels": info.channels,
        "format": info.format,
        "sha256": digest,
    }


def load_source(name: str, data_dir: Path) -> list[dict]:
    root = data_dir / "raw" / name
    rows = LOADERS[name].load(root)
    manifest.check_rows(rows, name)
    for row in rows:
        row["path"] = f"raw/{name}/{row['path']}"
    return rows


def build(data_dir: Path, names: list[str], workers: int = 8) -> pd.DataFrame:
    rows = []
    for name in names:
        source_rows = load_source(name, data_dir)
        print(f"{name}: {len(source_rows)} clips")
        rows.extend(source_rows)

    df = pd.DataFrame(rows, columns=manifest.LABEL_COLUMNS)
    repeated = df["utt_id"][df["utt_id"].duplicated()]
    if not repeated.empty:
        raise ValueError(f"utt_id is not unique, e.g. {repeated.iloc[0]}")

    with ThreadPoolExecutor(workers) as pool:
        audio = list(pool.map(describe, (data_dir / p for p in df["path"])))
    return pd.concat([df, pd.DataFrame(audio, index=df.index)], axis=1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sources", nargs="*", help=f"any of {sorted(LOADERS)}; default: all present")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    unknown = [s for s in args.sources if s not in LOADERS]
    if unknown:
        sys.exit(f"Unknown source(s) {unknown}; choose from {sorted(LOADERS)}")
    names = args.sources or [n for n in LOADERS if (args.data_dir / "raw" / n).is_dir()]
    if not names:
        sys.exit(f"No datasets found under {args.data_dir / 'raw'}; see README.md")

    df = build(args.data_dir, names, args.workers)
    out = args.data_dir / "manifest.parquet"
    manifest.save(df, out)
    print(f"Wrote {len(df)} clips to {out}")


if __name__ == "__main__":
    main()
