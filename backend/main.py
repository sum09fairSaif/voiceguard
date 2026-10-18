from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from routers import auth, challenge, verify
from transcription import TranscriptionUnavailable

app = FastAPI(title="VoiceGuard API", version="0.1.0")

# CORS lets the frontend (a different address) call this API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(challenge.router)
app.include_router(verify.router)


@app.exception_handler(RequestValidationError)
def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Say which field is wrong, but never echo back what was sent:
    # it could be a password.
    errors = [{key: e[key] for key in ("type", "loc", "msg")} for e in exc.errors()]
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": errors})


@app.exception_handler(PyMongoError)
def database_error(request: Request, exc: PyMongoError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "The service is temporarily unavailable. Please try again shortly."},
    )


@app.exception_handler(TranscriptionUnavailable)
def transcription_unavailable(request: Request, exc: TranscriptionUnavailable) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Voice checks are temporarily unavailable. Please try again shortly."},
    )

@app.get("/health")
def health():
    return {"status": "ok", "service": "voiceguard-api"}
