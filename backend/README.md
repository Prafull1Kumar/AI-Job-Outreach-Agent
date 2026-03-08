# Backend - AI Job Outreach Agent

## Run

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload --port 8000
```

## API Endpoints

- `GET /health`
- `POST /parse-job` (supports `job_description` or `job_link`)
- `POST /extract-keywords` (extract keywords from provided JD or URL)
- `POST /draft-email`
- `POST /send-email`
- `POST /draft-email-upload` (multipart form, supports resume file upload)
- `POST /send-email-upload` (multipart form, supports resume file upload)

## Skill Taxonomy (O*NET/ESCO)

To enrich technology extraction from open data:

```bash
cd backend
source .venv/bin/activate
python scripts/fetch_onet_tech_skills.py
```

This stores files in `backend/data/taxonomy/`, and `job_service.py` auto-loads them.

Optional custom source paths via `.env`:

```env
TECH_TAXONOMY_PATHS=/abs/path/tech_phrases.json,/abs/path/skills.csv
```

## Where To Implement LLM + RAG

- `app/services/llm_service.py`
  - `TODO(LLM)` in `parse_job_description`
  - `TODO(LLM)` in `draft_outreach_email`
- `app/services/rag_service.py`
  - `TODO(RAG)` in `retrieve_resume_evidence`
- `app/services/resume_service.py`
  - Optional place to add OCR/advanced resume parsing for scanned PDFs
- `app/services/outreach_service.py`
  - `TODO(OUTREACH)` if you want Gmail API OAuth instead of SMTP
