# ============================================================================
# RunPod Serverless Worker — Faster-Whisper Transcription
#
# Build:
#   docker build --platform linux/amd64 -t nicholasjacob1990/faster-whisper-diarize:v2 .
#
# Test locally:
#   docker run --rm --gpus all -p 8080:8080 nicholasjacob1990/faster-whisper-diarize:v2
#
# Push:
#   docker push nicholasjacob1990/faster-whisper-diarize:v2
# ============================================================================

FROM runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Pre-download Whisper model at build time (avoids cold-start download)
ARG WHISPER_MODEL=large-v3
ENV WHISPER_MODEL=${WHISPER_MODEL}
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('${WHISPER_MODEL}', device='cpu', compute_type='int8')" && \
    echo "Model ${WHISPER_MODEL} cached successfully"

# Copy handler
COPY rp_handler.py .

# RunPod serverless entry point
CMD ["python", "-u", "rp_handler.py"]
