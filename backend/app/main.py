import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.schemas import (
    DraftEmailResponse,
    JobOutreachRequest,
    ParsedJob,
    SendEmailResponse,
)
from app.services.llm_service import draft_outreach_email, parse_job_description
from app.services.outreach_service import send_email_via_gmail
from app.services.rag_service import retrieve_resume_evidence

load_dotenv()

app = FastAPI(title="AI Job Outreach Agent API", version="1.0.0")

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin, "http://127.0.0.1:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/parse-job", response_model=ParsedJob)
def parse_job(payload: JobOutreachRequest) -> ParsedJob:
    return parse_job_description(payload.job_description)


@app.post("/draft-email", response_model=DraftEmailResponse)
def draft_email(payload: JobOutreachRequest) -> DraftEmailResponse:
    parsed = parse_job_description(payload.job_description)
    retrieval_query = f"{parsed.role} {' '.join(parsed.key_requirements)} {payload.recruiter_profile}"
    evidence = retrieve_resume_evidence(retrieval_query, payload.resume_text)
    return draft_outreach_email(
        recruiter_name=payload.recruiter_name,
        recruiter_profile=payload.recruiter_profile,
        parsed_job=parsed,
        evidence=evidence,
    )


@app.post("/send-email", response_model=SendEmailResponse)
def send_email(payload: JobOutreachRequest) -> SendEmailResponse:
    parsed = parse_job_description(payload.job_description)
    retrieval_query = f"{parsed.role} {' '.join(parsed.key_requirements)} {payload.recruiter_profile}"
    evidence = retrieve_resume_evidence(retrieval_query, payload.resume_text)
    draft = draft_outreach_email(
        recruiter_name=payload.recruiter_name,
        recruiter_profile=payload.recruiter_profile,
        parsed_job=parsed,
        evidence=evidence,
    )

    return send_email_via_gmail(payload.recruiter_email, draft.subject, draft.body)
