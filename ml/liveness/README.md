# Liveness datasets

Tools for gathering the audio used to test (and later fine-tune) the
liveness check, story #17. Nothing here is deployed: the live check only
needs AASIST's weights. This is for measuring how well it works.

## The datasets

| Source | What it gives us | Labels | Split | Size | License |
|---|---|---|---|---|---|
| `asvspoof2019_la` | The standard benchmark: VCTK speech plus 19 TTS and voice-conversion attacks. AASIST was trained on it. | bonafide + spoof | official train / dev / eval (eval becomes `test`) | ~7 GB | ODC-By 1.0 |
| `asvspoof2019_pa` | Replay attacks: VCTK speech played back through simulated rooms and replay devices of three quality levels. Our only replay data. | bonafide + spoof | official train / dev / eval | ~18 GB | ODC-By 1.0 |
| `asvspoof5` | The 2024 ASVspoof: ~2,000 crowdsourced speakers in varied conditions, 32 modern and adversarial attacks, most eval clips codec-compressed. | bonafide + spoof | official train / dev / eval | dev + 1 eval part ~29 GB (full: 143 GB) | ODC-By 1.0 |
| `in_the_wild` | Real deepfakes of public figures, made with unknown tools. Our generalization test. | bonafide + spoof | test only | ~8 GB | research use, see source |
| `codecfake` | VCTK speech re-synthesized by 15 neural codecs, the technology behind zero-shot voice cloning. Same speakers as ASVspoof 2019. | bonafide + spoof | by speaker, ~80/10/10 | 16 shards ~10 GB (full: 102 GB) | CC-BY-4.0 |
| `common_voice` | English speakers recorded in their browsers on everyday mics, like our users. Stops "cheap mic" being mistaken for "fake". Reads current releases or the 2017 Kaggle one (no speaker ids). | bonafide | official train / dev / test, a fixed slice of each | slice of the English set | CC0 1.0 |
| `team` | Our own recordings through the app: live reads, replays and consented voice clones. The threshold is chosen on this. | bonafide + spoof | dev / test only, never trained on | small | private, team only |

The datasets hosted on Hugging Face are fetched by a script, which takes a
manageable slice of each (see its docstring for options):

```
python download.py asvspoof5
python download.py codecfake
```

Downloads resume after a dropped connection, so rerun a command if it
stops. For gated datasets, accept the terms on the dataset's page while
logged in to huggingface.co, then run `huggingface-cli login` once.

The others are downloaded by hand: where to get each one, and how to unzip
it, is at the top of its loader in [sources/](sources/).

## Where the audio goes

Unzip each dataset into `data/raw/<source>/` in this folder:

```
ml/liveness/data/          (git-ignored: audio is never committed)
  raw/
    asvspoof2019_la/LA/...
    asvspoof2019_pa/PA/...
    asvspoof5/ASVspoof5.*.tsv, flac_D/, flac_E_eval/
    in_the_wild/release_in_the_wild/...
    codecfake/metadata.csv, audio/<codec>/...
    common_voice/cv-corpus-*/en/...   (or cv-valid-*.csv + cv-valid-*/ from the 2017 release)
    team/metadata.csv, spk01/...
  manifest.parquet         (written by build_manifest.py)
  manifest.clean.parquet   (written by validate.py)
  issues.csv, report.md    (written by validate.py)
  processed/<source>/...   (written by preprocess.py, same folders as raw/)
  manifest.processed.parquet, preprocess_issues.csv, preprocess_report.md
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
python preprocess.py          # make every clip the same kind of audio
```

Read `data/report.md` before using the data. It shows how many clips each
source, split and label has, which clips were dropped and why, and whether
any speaker appears in more than one split.

## Preprocessing

`preprocess.py` writes a cleaned copy of every clip in the clean manifest,
across all splits, and leaves the raw audio alone. The full set took about
45 minutes with 18 workers and needs about 82 GB. It can be stopped at any
time, and rerunning it carries on from where it stopped.

Each clip goes through the steps in `audio.py`, which the live check should
reuse so that users' audio gets the same treatment:

1. **16 kHz mono.** Every 24 and 44.1 kHz clip we have is a fake, so leaving
   rates mixed would give the label away.
2. **Centre the wave on zero** (remove the DC offset). Fakes tend to sit
   slightly off centre: on its own this separates fakes from real clips well
   in CodecFake and ASVspoof 5.
3. **Trim the silence at both ends**, with no padding left, cutting anything
   30 dB below the loudest moment so background noise counts as silence. In ASVspoof 2019
   LA, real clips have about 0.7 s of silence at the start and fakes have
   almost none, so a model can score well just by spotting a pause.
4. **Bring the speech to the same loudness** (-26 dBFS, less if that would clip).

Clips stay full length. `audio.fix_length()` cuts them to AASIST's 64,600
samples when they're loaded: a random window in training, the start of the
clip when scoring.

Later steps read `manifest.processed.parquet`: the columns below, plus
`raw_path`, `lead_trim_s`, `tail_trim_s` and `gain_db`. Check
`data/preprocess_report.md` to see what was trimmed from real and fake clips.
A clip left with under 0.5 seconds of audio is dropped as `too_short_after_trim`.

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
- **corrupt**: a sample value that real audio can't have (over 2.0)
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

Speaker-safe splits for team data, augmentation (browser codecs, RawBoost,
noise) and scoring pretrained AASIST on ASVspoof 2019 LA and In-the-Wild.
AASIST was trained on untrimmed audio, so score it on both the raw and the
processed clips to see what preprocessing changes. To compare with published
scores, use the raw clips in `manifest.parquet`: validate.py's 1-second limit
removes some official ASVspoof 2019 test clips from the clean manifest.

## Tests

```
pip install -r requirements-dev.txt
python -m pytest
```

The tests build tiny fake datasets out of sine tones, so they need no downloads.
