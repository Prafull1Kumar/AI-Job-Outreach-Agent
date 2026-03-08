# Backend - AI Job Outreach Agent

## Run

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

## API Endpoints

- `GET /health`
- `POST /parse-job`
- `POST /draft-email`
- `POST /send-email`

## Where To Implement LLM + RAG

- `app/services/llm_service.py`
  - `TODO(LLM)` in `parse_job_description`
  - `TODO(LLM)` in `draft_outreach_email`
- `app/services/rag_service.py`
  - `TODO(RAG)` in `retrieve_resume_evidence`
- `app/services/outreach_service.py`
  - `TODO(OUTREACH)` if you want Gmail API OAuth instead of SMTP
