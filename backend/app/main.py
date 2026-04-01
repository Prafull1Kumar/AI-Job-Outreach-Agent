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
    JobSummaryResponse,
    ParsedJob,
    SendEmailResponse,
)
from app.services.job_service import resolve_job_summary_input, resolve_job_text_and_keywords
from app.services.llm_service import (
    draft_outreach_email,
    parse_job_description,
    summarize_job_for_email_prompt,
)
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


def _resolve_current_email(
    provided_subject: Optional[str],
    provided_body: Optional[str],
    generated_draft: DraftEmailResponse,
) -> tuple[str, str]:
    subject = (provided_subject or "").strip() or generated_draft.subject
    body = (provided_body or "").strip() or generated_draft.body
    return subject, body


def _build_retrieval_query(
    parsed_job: ParsedJob,
    recruiter_profile: str,
    job_summary: JobSummaryResponse,
) -> str:
    parts = [
        parsed_job.role,
        parsed_job.company,
        " ".join(parsed_job.key_requirements),
        recruiter_profile.strip(),
    ]

    structured = job_summary.structured_summary or {}
    for key in ["role_overview", "company_overview"]:
        value = structured.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())

    for key in ["key_responsibilities", "requirements"]:
        value = structured.get(key)
        if isinstance(value, list):
            parts.append(" ".join(str(item).strip() for item in value if str(item).strip()))
        elif isinstance(value, str) and value.strip():
            parts.append(value.strip())

    return " ".join(part for part in parts if part).strip()


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
        resolved_job_description_preview=job_text,
    )


@app.post("/summarize-job", response_model=JobSummaryResponse)
def summarize_job(payload: JobContentRequest) -> JobSummaryResponse:
    try:
        job_summary_input = resolve_job_summary_input(
            payload.job_description,
            str(payload.job_link) if payload.job_link else None,
        )
        job_text, extracted_keywords = resolve_job_text_and_keywords(
            payload.job_description,
            str(payload.job_link) if payload.job_link else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parsed = parse_job_description(job_text, extracted_keywords=extracted_keywords)
    summarized = summarize_job_for_email_prompt(job_summary_input, extracted_keywords)
    return JobSummaryResponse(
        source=summarized.source,
        company_name=parsed.company,
        job_name=parsed.role,
        extracted_keywords=extracted_keywords,
        summary=summarized.summary,
        structured_summary=summarized.structured_summary,
        email_generation_prompt=summarized.email_generation_prompt,
        llm_used=summarized.llm_used,
        llm_error=summarized.llm_error,
    )


@app.post("/draft-email", response_model=DraftEmailResponse)
def draft_email(payload: JobOutreachRequest) -> DraftEmailResponse:
    try:
        job_summary_input = resolve_job_summary_input(
            payload.job_description,
            str(payload.job_link) if payload.job_link else None,
        )
        job_text, extracted_keywords = resolve_job_text_and_keywords(
            payload.job_description,
            str(payload.job_link) if payload.job_link else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parsed = parse_job_description(job_text, extracted_keywords=extracted_keywords)
    job_summary = summarize_job_for_email_prompt(job_summary_input, extracted_keywords)
    retrieval_query = _build_retrieval_query(parsed, payload.recruiter_profile, job_summary)
    evidence = retrieve_resume_evidence(retrieval_query, payload.resume_text)
    return draft_outreach_email(
        recruiter_name=payload.recruiter_name,
        recruiter_profile=payload.recruiter_profile,
        parsed_job=parsed,
        evidence=evidence,
        job_summary_prompt=job_summary.email_generation_prompt,
    )


@app.post("/send-email", response_model=SendEmailResponse)
def send_email(payload: JobOutreachRequest) -> SendEmailResponse:
    if (payload.email_subject or "").strip() and (payload.email_body or "").strip():
        return send_email_via_gmail(
            payload.recruiter_email,
            payload.email_subject.strip(),
            payload.email_body.strip(),
        )

    try:
        job_text, extracted_keywords = resolve_job_text_and_keywords(
            payload.job_description,
            str(payload.job_link) if payload.job_link else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parsed = parse_job_description(job_text, extracted_keywords=extracted_keywords)
    draft = draft_outreach_email(
        recruiter_name=payload.recruiter_name,
        recruiter_profile=payload.recruiter_profile,
        parsed_job=parsed,
        evidence=[],
    )
    subject, body = _resolve_current_email(payload.email_subject, payload.email_body, draft)

    return send_email_via_gmail(payload.recruiter_email, subject, body)


@app.post("/draft-email-upload", response_model=DraftEmailResponse)
def draft_email_upload(
    recruiter_name: str = Form(...),
    recruiter_profile: str = Form(...),
    job_description: str = Form(""),
    job_link: str = Form(""),
    resume_text: str = Form(""),
    email_subject: str = Form(""),
    email_body: str = Form(""),
    resume_file: Optional[UploadFile] = File(None),
) -> DraftEmailResponse:
    try:
        final_resume_text = resolve_resume_text(resume_text, resume_file)
        job_summary_input = resolve_job_summary_input(
            job_description or None,
            job_link or None,
        )
        final_job_text, extracted_keywords = resolve_job_text_and_keywords(
            job_description or None,
            job_link or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parsed = parse_job_description(final_job_text, extracted_keywords=extracted_keywords)
    job_summary = summarize_job_for_email_prompt(job_summary_input, extracted_keywords)
    retrieval_query = _build_retrieval_query(parsed, recruiter_profile, job_summary)
    evidence = retrieve_resume_evidence(retrieval_query, final_resume_text)

    draft = draft_outreach_email(
        recruiter_name=recruiter_name,
        recruiter_profile=recruiter_profile,
        parsed_job=parsed,
        evidence=evidence,
        job_summary_prompt=job_summary.email_generation_prompt,
    )
    subject, body = _resolve_current_email(email_subject, email_body, draft)
    return DraftEmailResponse(
        subject=subject,
        body=body,
        evidence_used=draft.evidence_used,
        job_summary_prompt=draft.job_summary_prompt,
    )


@app.post("/send-email-upload", response_model=SendEmailResponse)
def send_email_upload(
    recruiter_name: str = Form(...),
    recruiter_email: str = Form(...),
    recruiter_profile: str = Form(...),
    job_description: str = Form(""),
    job_link: str = Form(""),
    resume_text: str = Form(""),
    email_subject: str = Form(""),
    email_body: str = Form(""),
    resume_file: Optional[UploadFile] = File(None),
) -> SendEmailResponse:
    if email_subject.strip() and email_body.strip():
        return send_email_via_gmail(recruiter_email, email_subject.strip(), email_body.strip())

    try:
        final_job_text, extracted_keywords = resolve_job_text_and_keywords(
            job_description or None,
            job_link or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parsed = parse_job_description(final_job_text, extracted_keywords=extracted_keywords)
    draft = draft_outreach_email(
        recruiter_name=recruiter_name,
        recruiter_profile=recruiter_profile,
        parsed_job=parsed,
        evidence=[],
    )
    subject, body = _resolve_current_email(email_subject, email_body, draft)
    return send_email_via_gmail(recruiter_email, subject, body)
