import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    DraftEmailResponse,
    JobContentRequest,
    JobExtractionResponse,
    JobOutreachRequest,
    ParsedJob,
    SendEmailResponse,
)
from app.services.job_service import resolve_job_text_and_keywords
from app.services.llm_service import draft_outreach_email, parse_job_description
from app.services.outreach_service import send_email_via_gmail
from app.services.rag_service import retrieve_resume_evidence
from app.services.resume_service import resolve_resume_text

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
def parse_job(payload: JobContentRequest) -> ParsedJob:
    try:
        job_text, extracted_keywords = resolve_job_text_and_keywords(
            payload.job_description,
            str(payload.job_link) if payload.job_link else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return parse_job_description(job_text, extracted_keywords=extracted_keywords)


@app.post("/extract-keywords", response_model=JobExtractionResponse)
def extract_keywords(payload: JobContentRequest) -> JobExtractionResponse:
    try:
        job_text, extracted_keywords = resolve_job_text_and_keywords(
            payload.job_description,
            str(payload.job_link) if payload.job_link else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    source = "job_description" if payload.job_description else "job_link"
    return JobExtractionResponse(
        source=source,
        keyword_count=len(extracted_keywords),
        extracted_keywords=extracted_keywords,
        resolved_job_description_preview=job_text[:500],
    )


@app.post("/draft-email", response_model=DraftEmailResponse)
def draft_email(payload: JobOutreachRequest) -> DraftEmailResponse:
    try:
        job_text, extracted_keywords = resolve_job_text_and_keywords(
            payload.job_description,
            str(payload.job_link) if payload.job_link else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parsed = parse_job_description(job_text, extracted_keywords=extracted_keywords)
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
    try:
        job_text, extracted_keywords = resolve_job_text_and_keywords(
            payload.job_description,
            str(payload.job_link) if payload.job_link else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parsed = parse_job_description(job_text, extracted_keywords=extracted_keywords)
    retrieval_query = f"{parsed.role} {' '.join(parsed.key_requirements)} {payload.recruiter_profile}"
    evidence = retrieve_resume_evidence(retrieval_query, payload.resume_text)
    draft = draft_outreach_email(
        recruiter_name=payload.recruiter_name,
        recruiter_profile=payload.recruiter_profile,
        parsed_job=parsed,
        evidence=evidence,
    )

    return send_email_via_gmail(payload.recruiter_email, draft.subject, draft.body)


@app.post("/draft-email-upload", response_model=DraftEmailResponse)
def draft_email_upload(
    recruiter_name: str = Form(...),
    recruiter_profile: str = Form(...),
    job_description: str = Form(""),
    job_link: str = Form(""),
    resume_text: str = Form(""),
    resume_file: Optional[UploadFile] = File(None),
) -> DraftEmailResponse:
    try:
        final_resume_text = resolve_resume_text(resume_text, resume_file)
        final_job_text, extracted_keywords = resolve_job_text_and_keywords(
            job_description or None,
            job_link or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parsed = parse_job_description(final_job_text, extracted_keywords=extracted_keywords)
    retrieval_query = f"{parsed.role} {' '.join(parsed.key_requirements)} {recruiter_profile}"
    evidence = retrieve_resume_evidence(retrieval_query, final_resume_text)

    return draft_outreach_email(
        recruiter_name=recruiter_name,
        recruiter_profile=recruiter_profile,
        parsed_job=parsed,
        evidence=evidence,
    )


@app.post("/send-email-upload", response_model=SendEmailResponse)
def send_email_upload(
    recruiter_name: str = Form(...),
    recruiter_email: str = Form(...),
    recruiter_profile: str = Form(...),
    job_description: str = Form(""),
    job_link: str = Form(""),
    resume_text: str = Form(""),
    resume_file: Optional[UploadFile] = File(None),
) -> SendEmailResponse:
    try:
        final_resume_text = resolve_resume_text(resume_text, resume_file)
        final_job_text, extracted_keywords = resolve_job_text_and_keywords(
            job_description or None,
            job_link or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parsed = parse_job_description(final_job_text, extracted_keywords=extracted_keywords)
    retrieval_query = f"{parsed.role} {' '.join(parsed.key_requirements)} {recruiter_profile}"
    evidence = retrieve_resume_evidence(retrieval_query, final_resume_text)

    draft = draft_outreach_email(
        recruiter_name=recruiter_name,
        recruiter_profile=recruiter_profile,
        parsed_job=parsed,
        evidence=evidence,
    )
    return send_email_via_gmail(recruiter_email, draft.subject, draft.body)
