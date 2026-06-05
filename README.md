# Adaptive Tutor

Subject-agnostic AI tutor prototype for testing curriculum-grounded explanations, adaptive learning modes, short assessment checks, and reflection logs.

## Run Locally With Git Bash

**Prerequisites:** Python 3.11+ and Node.js 20+

### 1. Python Backend

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Set `GEMINI_API_KEY` in `.env` for live model calls. Without it, the backend runs in demo fallback mode.

### 2. React Frontend

Open a second terminal:

```bash
npm.cmd install
npm.cmd run dev
```

The frontend runs on `http://localhost:5173` and proxies `/api/*` requests to the FastAPI backend on `http://localhost:8000`.

## Useful Checks

```bash
curl http://localhost:8000/api/health
npm.cmd run lint
```

## Test RAG

Terminal-only retrieval test:

```bash
python test_rag.py "What does RuBisCO do in the Calvin Cycle?"
python test_rag.py "How is ATP made in chloroplasts?" --k 1
```

Backend RAG endpoint test:

```bash
curl -X POST http://localhost:8000/api/rag/search \
  -H "Content-Type: application/json" \
  -d '{"query":"What does RuBisCO do in the Calvin Cycle?","k":2}'
```

Chat endpoint test:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What does RuBisCO do in the Calvin Cycle?","language":"EN","mode":"step-step"}'
```

## Upload Sources

The Learning screen includes an upload control in the Source panel. The current prototype supports:

- PDF files with selectable/extractable text
- TXT files

Uploaded sources are stored in `data/uploads/`, extracted text is stored in `data/processed/`, and source metadata is appended to `data/sources.json`.

Scanned or image-only PDFs are not supported yet. Those will need OCR before they can be indexed.

For prototype testing, large PDFs are intentionally capped by:

```bash
MAX_UPLOAD_PAGES="35"
MAX_UPLOAD_CHUNKS="90"
```

This keeps indexing inside free-tier embedding limits. For full textbook ingestion, the product will need background indexing, persistent vector storage, and higher quota or local embeddings.

Backend upload test:

```bash
curl -X POST http://localhost:8000/api/sources/upload \
  -F "file=@WEEK_1_ONEPAGER_CLEAN (1).pdf"
```

## Git Bash Troubleshooting

If Git Bash says `npm: command not found`, use `npm.cmd` instead:

```bash
npm.cmd install
npm.cmd run dev
```

If `npm.cmd` is also not found, install Node.js LTS from `https://nodejs.org/`, close Git Bash, reopen it, and check:

```bash
node --version
npm.cmd --version
```
