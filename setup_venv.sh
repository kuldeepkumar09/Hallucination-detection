#!/usr/bin/env bash
# ============================================================
#  Hallucination Detection Middleware — Virtual Environment Setup
#  Run once: bash setup_venv.sh
#  After setup: source venv/bin/activate && python run_proxy.py
# ============================================================
set -e

echo ""
echo "[1/5] Checking Python..."
python3 --version || { echo "ERROR: python3 not found. Install Python 3.11+"; exit 1; }

echo ""
echo "[2/5] Creating virtual environment..."
python3 -m venv venv

echo ""
echo "[3/5] Activating virtual environment..."
source venv/bin/activate

echo ""
echo "[4/5] Installing dependencies (this may take a few minutes)..."
pip install --upgrade pip --quiet
pip install -r requirements.txt

echo ""
echo "[5/5] Downloading spaCy language model..."
python -m spacy download en_core_web_sm || echo "WARNING: spaCy model download failed — fallback splitter will be used."

echo ""
echo "============================================================"
echo " Setup complete!"
echo " To start the server:"
echo "   source venv/bin/activate && python run_proxy.py"
echo " GPU support: auto-detected (CUDA if NVIDIA GPU present)"
echo "============================================================"
echo ""
