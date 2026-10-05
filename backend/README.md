# VoiceGuard backend

FastAPI service.

## Run locally

From the `backend/` folder:

1. Create a virtual environment (an isolated Python for this project):
   `python -m venv venv`
2. Activate it:
   - macOS / Linux: `source venv/bin/activate`
   - Windows: `venv\Scripts\activate`
3. Install packages: `pip install -r requirements.txt`
4. Start the server: `uvicorn main:app --reload --port 8000`
5. Check it: open http://localhost:8000/health
   You should see: {"status":"ok","service":"voiceguard-api"}

Interactive API docs are at http://localhost:8000/docs