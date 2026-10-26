# Liveness datasets

Tools for gathering the audio used to test (and later fine-tune) the
liveness check, story #17. Nothing here is deployed: the live check only
needs AASIST's weights. This is for measuring how well it works.

## The datasets

| Source | What it gives us | Labels | Split | Size | License |
|---|---|---|---|---|---|
| `asvspoof2019_la` | The standard benchmark: VCTK speech plus 19 TTS and voice-conversion attacks. AASIST was trained on it. | bonafide + spoof | official train / dev / eval (eval becomes `test`) | ~7 GB | ODC-By 1.0 |
| `in_the_wild` | Real deepfakes of public figures, made with unknown tools. Our generalization test. | bonafide + spoof | test only | ~8 GB | research use, see source |
| `common_voice` | English speakers recorded in their browsers on everyday mics, like our users. Stops "cheap mic" being mistaken for "fake". | bonafide | official train / dev / test, a few clips per speaker | slice of the English set | CC0 1.0 |
| `team` | Our own recordings through the app: live reads, replays and consented voice clones. The threshold is chosen on this. | bonafide + spoof | dev / test only, never trained on | small | private, team only |

Where to download each one, and how to unzip it, is at the top of its loader
in [sources/](sources/). Most require accepting terms on the download page,
so they're downloaded by hand rather than by a script.

## Where the audio goes

Unzip each dataset into `data/raw/<source>/` in this folder:

```
ml/liveness/data/          (git-ignored: audio is never committed)
  raw/
    asvspoof2019_la/LA/...
    in_the_wild/release_in_the_wild/...
    common_voice/cv-corpus-*/en/...
    team/metadata.csv, spk01/...
  manifest.parquet         (written by build_manifest.py)
  manifest.clean.parquet   (written by validate.py)
  issues.csv, report.md    (written by validate.py)
```

To keep the audio somewhere else (an external drive, a cloud volume), pass
`--data-dir` to both scripts.

Team recordings are biometric data. Everyone recorded must give written
consent first, speaker ids are codes like `spk01`, never names, and the
files are shared only through the team's private storage, never in git or
chat.

## Running it

From `ml/liveness/`:

```
python -m venv .venv
.venv/Scripts/activate        # Windows; on macOS or Linux: source .venv/bin/activate
pip install -r requirements.txt

python build_manifest.py      # list every clip from every dataset present
python validate.py            # check them all and write data/report.md
```

Read `data/report.md` before using the data. It shows how many clips each
source, split and label has, which clips were dropped and why, and whether
any speaker appears in more than one split.

## The manifest

Every later step reads `manifest.clean.parquet` instead of the datasets
themselves. One row per clip:

| Column | Meaning |
|---|---|
| `utt_id` | Unique id, `<source>/<the dataset's own id>` |
| `path` | Relative to the data folder |
| `source` | Which dataset |
| `speaker_id` | `<source>/<speaker>` |
| `label` | `bonafide` (live human) or `spoof` |
| `attack_type` | How a spoof was made, e.g. `A07`, `replay`, `unknown`; blank if bonafide |
| `split` | `train`, `dev` or `test` |
| `license` | The dataset's license |
| `duration_s`, `sample_rate`, `channels`, `format` | From the file |
| `sha256` | Hash of the file, for finding duplicates |

## What validate.py drops

- **missing** or **unreadable** files
- **too_short**: under 1 second
- **silent**: loudest sample under about -40 dBFS
- **clipped**: more than 1% of samples at full scale
- **duplicate**: an exact copy of an earlier clip (the first copy is kept)
- **duplicate_conflict**: the same file with different labels or splits
  (every copy is dropped, since we can't tell which is right)

Speakers found in more than one split are reported but not dropped: fix the
split instead, or the test score will be too good to be true.

## Adding a dataset

Write a module in `sources/` with a `NAME` and a `load(root)` that returns
manifest rows (copy an existing one), add it to `sources/__init__.py`, and
add a test in `tests/test_sources.py` with a miniature copy of its layout.

## Next steps

Preprocessing (16 kHz mono, the same silence trimming and loudness for every
clip, cropping to AASIST's 4 seconds), speaker-safe splits for team data,
augmentation (browser codecs, RawBoost, noise) and scoring pretrained AASIST
on ASVspoof 2019 LA and In-the-Wild.

## Tests

```
pip install -r requirements-dev.txt
python -m pytest
```

The tests build tiny fake datasets out of sine tones, so they need no downloads.
