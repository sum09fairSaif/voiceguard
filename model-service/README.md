---
title: VoiceGuard Model Service
sdk: gradio
sdk_version: 6.29.1
python_version: "3.11"
app_file: app.py
pinned: false
---

# VoiceGuard model service

Turns a recording into a speaker embedding (192 numbers that describe a
voice) with SpeechBrain's ECAPA model, `speechbrain/spkrec-ecapa-voxceleb`.
The VoiceGuard backend calls it for the identity check and enrollment. It
runs on its own because the model needs PyTorch, which is too big for the
backend's Render instance.

It runs as a Hugging Face Space on **ZeroGPU**, the free hardware for
Gradio Spaces. ZeroGPU only works for Gradio apps, so this is a Gradio app
with one API endpoint and no UI. The embedding runs in a `@spaces.GPU`
function; if no GPU is free (or the quota is used up) it falls back to the
CPU, which takes about half a second.

Recordings are never stored. They arrive as base64 text, so Gradio never
saves them as uploaded files, and each one is written to a temporary file
only while ffmpeg decodes it, then deleted.

## API

One endpoint, `embed`, over Gradio's HTTP API. It takes three strings:
the service token, the recording as base64, and its file extension
(`.webm`, `.ogg`, `.mp4`, `.m4a`, `.mp3` or `.wav`). The recording must be
at most 1 MB and have at least 0.5 s of sound.

1. `POST /gradio_api/call/embed` with `{"data": [token, audio_base64, extension]}`
   returns `{"event_id": "..."}`.
2. `GET /gradio_api/call/embed/<event_id>` streams the result, ending with
   `event: complete` and a `data:` line holding a one-item list:
   - `{"embedding": [...], "model": "...", "speech_seconds": 2.1, "clipped_share": 0.0}`:
     `speech_seconds` is how much of the recording is loud enough to be
     voice, `clipped_share` the share of samples cut off at full volume
     (0 to 1). The backend uses these to turn away poor enrollment samples.
   - or `{"error": "..."}`: `unauthorized` (wrong token),
     `service_token_not_set`, `unsupported_format`, `too_large` or
     `not_audio`.

The backend's `embedding.py` makes these two calls.

## Deploy as a Hugging Face Space

The Space installs Gradio (version from the header of this README), the
apt packages in `packages.txt` (ffmpeg) and `requirements.txt`, then runs
`python app.py`.

1. On huggingface.co, create a new Space: SDK **Gradio**, template
   **Blank**, hardware **ZeroGPU** (the free option; CPU basic needs PRO),
   visibility **Public** (the backend calls it without a Hugging Face login
   by default; `embed` is protected by `SERVICE_TOKEN` instead).
2. In the Space's **Settings → Variables and secrets**, add a secret
   `SERVICE_TOKEN` with a long random value, e.g. from
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
3. Upload the files in this folder (`app.py`, `packages.txt`,
   `requirements.txt`, `README.md`, replacing the Space's own README) to
   the Space, or push them with git. The first build takes several minutes,
   and each start downloads the model (about 80 MB).
4. Once it shows **Running**, open `https://<your-username>-<space-name>.hf.space`:
   it shows a one-line page.
5. In the backend's environment (local `.env` and Render), set
   `EMBEDDING_SERVICE_URL` to that address and `EMBEDDING_SERVICE_TOKEN` to
   the same value as `SERVICE_TOKEN`. Optionally set
   `EMBEDDING_SERVICE_HF_TOKEN` to a Hugging Face access token (read
   access is enough): ZeroGPU then counts GPU time against that account
   instead of as anonymous use.

A free Space sleeps after a while without traffic; the first request after
that takes longer while it wakes up.

## Run it locally

Needs Python 3.11, ffmpeg on the PATH (or `FFMPEG_BINARY` pointing at it),
and about 450 MB of free memory. Without the `spaces` package (only on
Hugging Face) the model runs on the CPU.

```
pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt gradio==6.29.1
SERVICE_TOKEN=any-local-token PORT=7861 python app.py
```

The first start downloads the model (about 80 MB). In the backend's `.env`,
set `EMBEDDING_SERVICE_URL=http://127.0.0.1:7861` (not `localhost`: on
Windows that tries IPv6 first and adds about 2 seconds to every call) and
`EMBEDDING_SERVICE_TOKEN` to the same token.

## Run the tests

The tests call the request handler directly with a stand-in for the model,
so they need neither PyTorch nor Gradio, only ffmpeg on the PATH (or
`FFMPEG_BINARY` pointing at it).

```
pip install -r requirements-dev.txt
python -m pytest
```
