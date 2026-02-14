# ============================================================================
# RunPod Serverless Worker v3 — Unified Whisper + Diarization
#
# Features:
#   - BatchedInferencePipeline (2-4x speedup)
#   - Multi-model: large-v3 + large-v3-turbo (pre-cached)
#   - int8_float16 compute type (35% less VRAM)
#   - Integrated pyannote diarization (no separate endpoint)
#   - Optional WhisperX word alignment
#   - Generator handler (streaming via /stream/{job_id})
#   - FFmpeg audio preprocessing
#   - Legal hotwords, anti-hallucination
#
# Build:
#   docker build --platform linux/amd64 -t nicholasjacob1990/faster-whisper-diarize:v3 .
#
# Test locally:
#   docker run --rm --gpus all -p 8080:8080 nicholasjacob1990/faster-whisper-diarize:v3
#
# Push:
#   docker push nicholasjacob1990/faster-whisper-diarize:v3
# ============================================================================

FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

WORKDIR /app

# System deps (ffmpeg for audio preprocessing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Pre-download Whisper models at build time (avoids cold-start download)
# Both models cached — handler swaps based on input param
RUN python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('Systran/faster-whisper-large-v3'); \
snapshot_download('Systran/faster-whisper-large-v3-turbo'); \
print('Both models cached successfully')"

# Pre-download pyannote diarization model (requires HF_TOKEN at build time)
# If HF_TOKEN not available, diarization will download on first use
ARG HF_TOKEN=""
RUN if [ -n "$HF_TOKEN" ]; then \
    python -c "\
import os; os.environ['HF_TOKEN']='${HF_TOKEN}'; \
from pyannote.audio import Pipeline; \
Pipeline.from_pretrained('pyannote/speaker-diarization-3.1', use_auth_token='${HF_TOKEN}'); \
print('Diarization model cached')" || echo "Diarization model cache skipped (token issue)"; \
    else echo "HF_TOKEN not set — diarization model will download on first use"; fi

# Copy handler
COPY rp_handler.py .

# Environment defaults
ENV WHISPER_MODEL=large-v3-turbo
ENV WHISPER_DEVICE=cuda
ENV WHISPER_COMPUTE_TYPE=int8_float16
ENV WHISPER_BATCH_SIZE=16

# RunPod serverless entry point
CMD ["python", "-u", "rp_handler.py"]
