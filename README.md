# C-33

Base foundation for an autonomous AI system.

## Pillars

- Agent loop: iterative reasoning and action execution.
- Tools: explicit tool registry for web/API integrations.
- Memory: persistent-state interface, with an in-memory implementation for the foundation.

This repository intentionally contains no provider-specific AI integration, GitHub Actions, CI/CD pipeline, or heavy linting.

## Local run

Python 3.13.15 is the selected runtime baseline.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

Open http://127.0.0.1:8000/health
