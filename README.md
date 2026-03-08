# AI Job Outreach Agent

Full-stack starter for an agent-based outreach workflow:
- Parse job descriptions
- Retrieve resume evidence (RAG hook)
- Draft personalized recruiter emails (LLM hook)
- Send emails via Gmail

## Project Structure

- `backend/` FastAPI API
- `frontend/` static HTML/CSS/JS app

## Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

## Frontend Setup

From repo root:

```bash
cd frontend
python3 -m http.server 3000
```

Then open: `http://localhost:3000`

## LLM + RAG Implementation Points

- `backend/app/services/llm_service.py`
  - `TODO(LLM)` in `parse_job_description`
  - `TODO(LLM)` in `draft_outreach_email`
- `backend/app/services/rag_service.py`
  - `TODO(RAG)` in `retrieve_resume_evidence`
- `backend/app/services/outreach_service.py`
  - `TODO(OUTREACH)` for Gmail API OAuth-based sending
