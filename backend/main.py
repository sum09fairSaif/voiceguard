from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="VoiceGuard API", version="0.1.0")

# CORS lets the frontend (a different address) call this API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok", "service": "voiceguard-api"}

class VerifyResult(BaseModel):
    content: float
    identity: float
    liveness: float
    decision: str

@app.post("/api/verify", response_model=VerifyResult)
def verify():
    # Placeholder. Real content, identity, and liveness checks come later.
    return VerifyResult(content=0.0, identity=0.0, liveness=0.0, decision="stub")