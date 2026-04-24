# ── Stage 1: Build React SPA ────────────────────────────────────────────────
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python + CUDA 12.4 runtime ─────────────────────────────────────
# nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 is a confirmed stable tag.
# PyTorch cu128 wheels bundle their own CUDA 12.8 libs — the base image only
# needs to provide libcuda.so (the driver interface), which any cuda-runtime
# image supplies.  Driver 595.97 on the host supports CUDA ≤ 13.2, so 12.8
# wheels run without issue.
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 AS runtime
WORKDIR /app

# Python 3.10 is the default in Ubuntu 22.04; venv avoids system-package conflicts
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-dev python3-pip \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && ln -sf /usr/bin/python3 /usr/local/bin/python3

# Isolated venv
RUN python -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Set HF cache before model download so baked models are owned by appuser later
ENV HF_HOME=/app/.cache

# PyTorch CUDA 12.4 wheels — stable index, matches the cuda:12.4.1 base image.
# Driver 595.97 supports CUDA ≤ 13.2, so cu124 wheels run fine on this GPU.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu124

# Remaining dependencies (torch excluded to avoid pip downgrading it)
COPY requirements.txt ./
RUN grep -v "^torch" requirements.txt > requirements-notorch.txt \
    && pip install --no-cache-dir -r requirements-notorch.txt \
    && python -m spacy download en_core_web_sm \
    && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" \
    && python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

# Block HuggingFace network at runtime — models already baked in
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

# Application code
COPY hallucination_middleware/ ./hallucination_middleware/
COPY run_proxy.py ./

# Built frontend from Stage 1
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# gosu lets the entrypoint (root) fix volume permissions then drop to appuser
RUN apt-get update && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

# Non-root user — created here so su-exec can switch to it
RUN useradd -m -u 1000 appuser && chown -R appuser /app

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Entrypoint runs as root, fixes /data permissions, then drops to appuser
ENTRYPOINT ["/entrypoint.sh"]
