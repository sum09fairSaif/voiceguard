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

## Scoring the pretrained model

`score_baseline.py` scores public AASIST checkpoints on a sample of test clips,
before we train anything, so every later model has a number to beat. The model
code is in `models/aasist.py`, copied unchanged from the official ASVspoof 5
baseline (MIT licence). The weights come from two public repos, cloned into the
git-ignored `data/external/`:

```
pip install -r requirements-model.txt --extra-index-url https://download.pytorch.org/whl/cpu
git clone --depth 1 https://github.com/asvspoof-challenge/asvspoof5 data/external/asvspoof5
git clone --depth 1 https://github.com/clovaai/aasist data/external/clovaai-aasist
python score_baseline.py \
  --model asvspoof5=data/external/asvspoof5/Baseline-AASIST/models/weights/AASIST/best.pth \
  --model aasist2019=data/external/clovaai-aasist/models/weights/AASIST.pth
```

Each clip is scored twice, as raw audio (only made 16 kHz mono, as the
checkpoints were trained) and as preprocessed audio. On a CPU it scores about 5
clips a second. Results go to `data/baseline/report.md`. The clips come from
the clean manifest, so validate.py's 1-second limit leaves out some official
ASVspoof 2019 test clips: don't compare these numbers directly with published
ones.

First results (November 2026; EER %, 500 test clips per dataset and label, so
give or take about 3 points; 50 is guessing):

| Dataset | ASVspoof 5 model, raw | processed | 2019 LA model, raw | processed |
|---|---|---|---|---|
| ASVspoof 2019 LA | 35.2 | 43.0 | **0.8** | 29.4 |
| ASVspoof 2019 PA (replay) | 47.8 | 49.8 | 43.2 | 46.2 |
| ASVspoof 5 | **27.6** | 31.6 | 36.6 | 32.6 |
| CodecFake | 49.6 | 50.2 | 47.2 | 48.4 |
| In-the-Wild | 28.8 | 32.2 | 44.2 | 42.6 |
| Common Voice, real clips rejected | 35.8 | 16.0 | 34.2 | 45.2 |

Each model does well only on the dataset it was trained on (in bold), and is
close to guessing on replay and codec fakes. Neither is good enough to use as
it is, so we fine-tune on our own data. Both do worse on processed audio
because they were trained with the silence left in: the 2019 model's 0.8%
rises to 29.4% once the silence is trimmed, so much of that score came from the
silence, not the voice.

## Training

`train.py` fine-tunes AASIST from a public checkpoint (it needs a GPU to be
practical; on a CPU it runs, slowly, for testing):

```
python download.py rirs_noises   # room echoes and noise, once
python train.py --init data/external/asvspoof5/Baseline-AASIST/models/weights/AASIST/best.pth --name first-try
```

- **Sampling** (`training_data.py`): every batch is half real and half fake.
  Within each half, a dataset is drawn in proportion to the square root of its
  size, so ASVspoof 5 doesn't swamp the rest.
- **Augmentation** (`augment.py`), on real and fake clips with the same chances:
  room echo (25%), background noise at 5-25 dB below the speech (30%), and
  Opus or MP3 compression at 7-120 kbps (50%). Compression matters most:
  browsers record in Opus, and Common Voice's real clips are MP3, so without
  it "sounds compressed" would pass for "real". Run with `--no-noise` to skip
  the echo and noise if RIRS_NOISES isn't downloaded.
- **Checking**: after each epoch, the EER on a fixed dev sample, averaged
  over datasets. The best epoch is kept as `data/runs/<name>/best.pth`, which
  `score_baseline.py` can then score on the test split.
- **Stopping**: `last.pth` is saved after every epoch; `--resume` carries on.

### Training on Kaggle's free GPUs

Kaggle gives about 30 free GPU hours a week, in sessions of up to 9-12 hours.
`kaggle_pack.py` gets everything ready (see its docstring for details):

1. Make a Kaggle account, verify a phone number (needed for GPUs), and under
   Settings > API create a token. Save it as `access_token` (the newer
   `KGAT_` tokens) or `kaggle.json` (older ones) in `C:\Users\<you>\.kaggle\`
   (Windows) or `~/.kaggle/`. Never put it in the repo.
2. `pip install -r requirements-model.txt` (includes the Kaggle CLI). On
   Windows, run the `kaggle` commands below from inside the folder with
   `-p .`: Kaggle CLI 2.2.5 breaks on Windows paths given to `-p`.
3. `python kaggle_pack.py --user <kaggle-username>` packs the training clips
   and a dev sample into about 15 GB under `data/kaggle/data/` (clips cut to 5
   seconds, ASVspoof 5's fakes thinned to 80,000).
4. `kaggle datasets create -p data/kaggle/data`, once. It's private.
5. `kaggle kernels push -p data/kaggle/script` starts training on a GPU. The
   code goes inside the script, so after a code change only this step and
   `kaggle_pack.py --script-only` are needed, not another upload.
6. `kaggle kernels status <kaggle-username>/voiceguard-liveness-train`, then
   `kaggle kernels output <kaggle-username>/voiceguard-liveness-train -p data/kaggle/output`
   to download `runs/<name>/best.pth` and `log.csv`.
7. If a session stopped before the last epoch, `python kaggle_pack.py --user
   <kaggle-username> --script-only --resume` and push again: the next session
   carries on from the last one's `last.pth`. Kaggle only attaches the output
   of the last version that finished without an error, so after a crash
   there's nothing to carry on from: the script then stops at once and lists
   what it found, rather than starting over.

On Kaggle's GPU it trains about 17 clips a second, about 65-75 minutes an
epoch, so 10 epochs need two sessions. The GPU is mostly waiting: Opus and MP3
compression on Kaggle's 4 CPU cores is the bottleneck.

Caution: CodecFake and ASVspoof 2019 both use VCTK speakers under different
ids, so a speaker can be in one's train split and the other's test split.
In-the-Wild shares no speakers or data with training, so it's the fairest
test.

### First fine-tuned model

`first-try` (November 2026): 10 epochs on Kaggle from the ASVspoof 5
checkpoint, compression only (no echo or noise: RIRS_NOISES wasn't
downloadable). Its best dev EER, averaged over datasets, was 17.8%, at the
last epoch. Scored on processed test audio with:

```
python score_baseline.py --audio processed --per-group 500 --out-folder finetuned \
  --title "Fine-tuned vs pretrained" --model first-try=data/models/first-try.pth \
  --model asvspoof5=... --model aasist2019=...
```

| Dataset (EER %, processed audio) | 2019 LA model | ASVspoof 5 model | first-try |
|---|---|---|---|
| All, pooled | 40.5 | 39.9 | **27.3** |
| ASVspoof 2019 LA | 29.4 | 43.0 | **27.4** |
| ASVspoof 2019 PA (replay) | 46.2 | 49.8 | **25.8** |
| ASVspoof 5 | 32.6 | 31.6 | **22.8** |
| CodecFake | 48.4 | 50.2 | **30.2** |
| In-the-Wild | 42.6 | 32.2 | **22.4** |
| Common Voice, real clips rejected | 45.2 | 16.0 | **1.6** |

It beats both checkpoints everywhere, including In-the-Wild, which it never
trained on. But about one fake in four still passes, so it isn't good enough to
rely on yet. Test scores are worse than dev ones (ASVspoof 2019 LA: 27% against
14%) because LA's test set uses attack types not in training.

Known problem: soundfile 0.13.1 (needed for its `compression_level`) bundles
libsndfile 1.2.2, which rejects about half of the raw ASVspoof 2019 PA FLAC
files that 1.2.0 read. The processed data was made with the old version and is
fine, but rerunning preprocessing, or scoring raw audio, fails on those files
until this is fixed.

## Next steps

- Fix reading the raw ASVspoof 2019 PA files with the current soundfile.
- Train with room echo and noise once RIRS_NOISES can be downloaded.
- Team recordings (live and replayed), to test against our own microphones.
- Try a stronger front end (wav2vec 2.0 + AASIST), which generalises much
  better in published results but is heavier to train and host.
- Add the liveness check to the model service and `/api/verify`.

## Tests

```
pip install -r requirements-dev.txt
python -m pytest
```

The tests build tiny fake datasets out of sine tones, so they need no downloads.
