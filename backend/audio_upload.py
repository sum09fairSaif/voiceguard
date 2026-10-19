from fastapi import HTTPException, UploadFile, status

# Reading six words is a few seconds of compressed audio, around 100 KB.
# 1 MB is plenty, and uploads that size stay in memory instead of being
# written to a temporary file.
MAX_AUDIO_BYTES = 1024 * 1024

# What browsers record in, mapped to the file extension Whisper and the
# model service use to recognise the format. The uploaded filename is never trusted or used.
AUDIO_TYPES = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}


def read_recording(audio: UploadFile) -> tuple[bytes, str]:
    """Return the uploaded recording and its file extension, or refuse it
    if it isn't audio, is too large or is empty. Kept in memory only."""
    # Browsers send e.g. "audio/webm;codecs=opus", so drop the parameters.
    media_type = (audio.content_type or "").split(";")[0].strip().lower()
    extension = AUDIO_TYPES.get(media_type)
    if extension is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Please send the recording as audio (webm, ogg, mp4, mp3 or wav).",
        )

    recording = audio.file.read(MAX_AUDIO_BYTES + 1)
    if len(recording) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="The recording is too long. Please read just the passage.",
        )
    if not recording:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The recording is empty. Please try again.",
        )
    return recording, extension
