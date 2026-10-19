---
title: VoiceGuard Model Service
sdk: docker
app_port: 7860
pinned: false
---

# VoiceGuard model service

Turns a recording into a speaker embedding (192 numbers that describe a
voice) with SpeechBrain's ECAPA model, `speechbrain/spkrec-ecapa-voxceleb`.
The VoiceGuard backend calls it for the identity check. It runs on its own
because the model needs PyTorch, which is too big for the backend's Render
instance.

Recordings are never stored. Each one is written to a temporary file only
while ffmpeg decodes it, then deleted.

## API

- `GET /health` returns `{"status": "ok", "model": "..."}`.
- `POST /embed` with header `Authorization: Bearer <SERVICE_TOKEN>` and a
  multipart file field `audio` (webm, ogg, mp4, m4a, mp3 or wav, up to
  1 MB, at least 0.5 s of sound). Returns `{"embedding": [...], "model": "..."}`.
  Errors: 401 wrong token, 413 too large, 422 not readable audio,
  503 `SERVICE_TOKEN` not set on the service.

## Deploy as a Hugging Face Space

1. On huggingface.co, create a new Space: SDK **Docker**, template **Blank**,
   hardware **CPU basic** (free).
2. In the Space's **Settings → Variables and secrets**, add a secret
   `SERVICE_TOKEN` with a long random value, e.g. from
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
3. Upload the files in this folder (`app.py`, `Dockerfile`,
   `requirements.txt`, `README.md`) to the Space, or push them with git.
   The first build takes several minutes.
4. Check `https://<your-username>-<space-name>.hf.space/health`.
5. In the backend's environment (local `.env` and Render), set
   `EMBEDDING_SERVICE_URL` to that address and `EMBEDDING_SERVICE_TOKEN` to
   the same value as `SERVICE_TOKEN`.

A free Space sleeps after a while without traffic; the first request after
that takes longer while it wakes up.

## Run it locally

Needs Python 3.11, ffmpeg on the PATH (or `FFMPEG_BINARY` pointing at it),
and about 450 MB of free memory.

```
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 torchaudio==2.5.1
pip install -r requirements.txt
SERVICE_TOKEN=any-local-token uvicorn app:app --port 7861
```

The first start downloads the model (about 80 MB). In the backend's `.env`,
set `EMBEDDING_SERVICE_URL=http://127.0.0.1:7861` (not `localhost`: on
Windows that tries IPv6 first and adds about 2 seconds to every call) and
`EMBEDDING_SERVICE_TOKEN` to the same token.

## Run the tests

The tests use a stand-in for the model, so they don't need PyTorch, only
ffmpeg on the PATH (or `FFMPEG_BINARY` pointing at it).

```
pip install -r requirements-dev.txt
python -m pytest
```
