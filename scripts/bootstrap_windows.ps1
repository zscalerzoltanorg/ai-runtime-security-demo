$ErrorActionPreference = "Stop"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
  Write-Error "Python launcher (py) not found. Install Python 3.11+ first."
}

py -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

if (-not (Test-Path .env.local)) {
  Copy-Item .env.example .env.local
  Write-Host "Created .env.local from .env.example"
}

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host "Installing Ollama via winget..."
    winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
  } else {
    Write-Warning "winget not found. Install Ollama manually from https://ollama.com/download"
  }
}

if (Get-Command ollama -ErrorAction SilentlyContinue) {
  if (-not (Get-Process -Name ollama -ErrorAction SilentlyContinue)) {
    Write-Host "Starting Ollama runtime (ollama serve)..."
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 2
  } else {
    Write-Host "Ollama process appears to be running."
  }

  Write-Host "Pulling default model (llama3.2:1b)..."
  try {
    ollama pull llama3.2:1b | Out-Host
  } catch {
    Write-Warning "Could not pull model automatically. You can retry with: ollama pull llama3.2:1b"
  }
}

Write-Host "Bootstrap complete."
Write-Host "Next:"
Write-Host "  1) Set env for this session (if needed) and run: python app.py"
