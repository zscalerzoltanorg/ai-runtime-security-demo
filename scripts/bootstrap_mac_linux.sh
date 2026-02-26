#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.11+ first."
  exit 1
fi

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f .env.local ]; then
  cp .env.example .env.local
  echo "Created .env.local from .env.example"
fi

ensure_ollama_installed() {
  if command -v ollama >/dev/null 2>&1; then
    return 0
  fi

  os_name="$(uname -s)"
  if [ "$os_name" = "Darwin" ]; then
    if command -v brew >/dev/null 2>&1; then
      echo "Installing Ollama via Homebrew..."
      brew install --cask ollama
    else
      echo "Homebrew not found. Install Ollama from https://ollama.com/download"
      return 1
    fi
  elif [ "$os_name" = "Linux" ]; then
    if command -v curl >/dev/null 2>&1; then
      echo "Installing Ollama via official installer..."
      curl -fsSL https://ollama.com/install.sh | sh
    else
      echo "curl not found. Install Ollama manually from https://ollama.com/download"
      return 1
    fi
  else
    echo "Unsupported OS for automatic Ollama install. Install manually from https://ollama.com/download"
    return 1
  fi
}

ensure_ollama_running() {
  if pgrep -f "ollama serve" >/dev/null 2>&1; then
    echo "Ollama runtime is already running."
    return 0
  fi
  echo "Starting Ollama runtime (ollama serve)..."
  nohup ollama serve > .ollama-serve.log 2>&1 &
  sleep 2
}

if ensure_ollama_installed; then
  ensure_ollama_running || true
  echo "Pulling default model (llama3.2:1b)..."
  if ! ollama pull llama3.2:1b; then
    echo "Could not pull model automatically. You can retry with: ollama pull llama3.2:1b"
  fi
fi

echo "Bootstrap complete."
echo "Next:"
echo "  1) Load env + run app: set -a; source .env.local; set +a; python app.py"
