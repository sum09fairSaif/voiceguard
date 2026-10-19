# Hugging Face Space (Docker SDK). Runs on a free CPU Space.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Spaces run as user 1000.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

# CPU-only PyTorch is much smaller than the default build.
RUN pip install --no-cache-dir --user --index-url https://download.pytorch.org/whl/cpu \
    torch==2.5.1 torchaudio==2.5.1
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user app.py .
# Download the model while building, so a waking Space doesn't wait for it.
RUN python -c "from app import load_encoder; load_encoder()"

EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
