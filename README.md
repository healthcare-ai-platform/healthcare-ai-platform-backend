# Healthcare AI Platform Backend

A minimal FastAPI backend scaffold for the Healthcare AI Platform.

## Setup

1. Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -e .
```

3. Start the development server:

```bash
python -m uvicorn app.main:create_app --reload
```

## Available endpoints

- `GET /health` - health check
- `GET /patients` - sample patient list
