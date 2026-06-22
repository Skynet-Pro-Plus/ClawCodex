#!/usr/bin/env bash
# Bootstrap script for ClawCodex inside WSL.
# Sets up a virtual environment, installs dependencies, and runs the requested component.

set -e

REPO="/mnt/d/clawcodex"
cd "$REPO"

# Create a virtual environment if it doesn't exist.
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "[bootstrap] Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate the virtual environment.
source "$VENV_DIR/bin/activate"

# Upgrade pip inside the venv.
python -m pip install --upgrade pip

# Install project dependencies (idempotent) inside the venv.
python -m pip install -r requirements.txt

# Run the requested component using the venv's python.
if [ -z "$1" ]; then
    echo "[bootstrap] Starting FastAPI server..."
    uvicorn src.server.app:app --host 0.0.0.0 --port 8000
else
    if [ "$1" = "chat" ]; then
        echo "[bootstrap] Starting ClawCodex chat CLI..."
        python clawcodex_chat.py
    else
        echo "[bootstrap] Unknown argument: $1"
        echo "Usage: $0 [chat]"
        exit 1
    fi
fi