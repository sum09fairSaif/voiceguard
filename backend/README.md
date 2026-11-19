# VoiceGuard backend

FastAPI service: accounts, password sign-in, challenge passages, the voice
checks (`/api/verify`) and voice enrollment. See the
[main README](../README.md) for the endpoint list and how the parts fit
together.

## Run locally

Needs **Python 3.11** (CI and Render use it; newer versions may fail to
install the pinned packages).

From the `backend/` folder:

1. Create a virtual environment (an isolated Python for this project):
   - macOS / Linux: `python3.11 -m venv venv`
   - Windows: `py -3.11 -m venv venv`
2. Activate it:
   - macOS / Linux: `source venv/bin/activate`
   - Windows: `venv\Scripts\activate`
3. Install packages, including the test tools: `pip install -r requirements-dev.txt`
4. Make sure there's a `.env` file in the repository root (copied from
   `.env.example`) with at least `MONGO_URI` and `JWT_SECRET` filled in. The
   [main README](../README.md#1-clone-and-create-your-env) says where each
   value comes from. Without them, `/health` works and everything else
   answers 503.
5. Start the server: `uvicorn main:app --reload --port 8000`
6. Check it: open http://localhost:8000/health
   You should see: {"status":"ok","service":"voiceguard-api"}

Interactive API docs are at http://localhost:8000/docs once `DOCS_ENABLED=true`
is set in `.env` (they're off by default, and must stay off on the live server).

Request bodies are capped before anything reads them (`body_limit.py`): 16 KB
for JSON routes, and the 1 MB recording limit plus 64 KB of form overhead for
`/api/verify` and `/api/enroll/samples`. Anything bigger gets a 413. The whole body must arrive within 30 seconds (408 otherwise), so a stalled upload can't hold memory.

## Tests and lint

The tests use a fake in-memory database and stand-ins for OpenAI and the
model service, so they need no `.env`, network or API keys.

```
python -m pytest
ruff check .
```

## Code layout

- `main.py`: creates the app, CORS, and turns errors into clear responses
- `body_limit.py` and `security_headers.py`: refuse oversized requests and add
  security headers to every response
- `routers/`: the endpoints (`auth`, `challenge`, `verify`, `enroll`)
- `config.py`: every setting, read from the environment with defaults
- `db.py`: MongoDB collections and their indexes
- One module per check or rule: `content_check.py`, `identity_check.py`,
  `decision.py`, `rate_limit.py`, `login_lockout.py`, `enrollment.py`,
  `transcription_budget.py`
- `client_address.py`: which client sent a request (`CLIENT_IP_SOURCE`), for
  per-client limits. Set `CLIENT_IP_SOURCE=peer` locally; the live default
  reads Cloudflare's `CF-Connecting-IP`
- `transcription.py` (OpenAI Whisper) and `embedding.py` (model service):
  calls to outside services
- `scripts/save_voiceprint.py`: dev tool to give a test account a voiceprint
