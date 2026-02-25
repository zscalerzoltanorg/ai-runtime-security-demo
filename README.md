# Local LLM Demo (Python stdlib + Ollama)

Very small demo app for local testing.

## Quick start

1. Start Ollama:
   - `ollama serve`
2. Pull a small model (once):
   - `ollama pull llama3.2:1b`
3. Run app:
   - `python app.py`
4. Open:
   - `http://127.0.0.1:5000`

## Optional env vars

- `OLLAMA_MODEL` (default: `llama3.2:1b`)
- `OLLAMA_URL` (default: `http://127.0.0.1:11434`)
