from pydantic import AnyHttpUrl, BaseModel, EmailStr, Field, model_validator
from typing import List, Optional


class JobContentRequest(BaseModel):
    job_description: Optional[str] = None
    job_link: Optional[AnyHttpUrl] = None

    @model_validator(mode="after")
    def validate_job_input(self):
        has_valid_description = (
            self.job_description is not None and len(self.job_description.strip()) >= 20
        )
        if not has_valid_description and self.job_link is None:
            raise ValueError("Provide job_description (>=20 chars) or job_link.")
        return self


class JobOutreachRequest(JobContentRequest):
    recruiter_name: str = Field(..., min_length=2)
    recruiter_email: EmailStr
    recruiter_profile: str = Field(..., min_length=20)
    resume_text: str = Field(..., min_length=50)
    email_subject: Optional[str] = None
    email_body: Optional[str] = None


class ParsedJob(BaseModel):
    role: str
    company: str
    key_requirements: List[str]
    seniority: str


class EvidenceItem(BaseModel):
    snippet: str
    relevance_score: float


class DraftEmailResponse(BaseModel):
    subject: str
    body: str
    evidence_used: List[EvidenceItem]
    job_summary_prompt: Optional[str] = None


class SendEmailResponse(BaseModel):
    status: str
    message: str


class JobExtractionResponse(BaseModel):
    source: str
    keyword_count: int
    extracted_keywords: List[str]
    resolved_job_description_preview: str


class JobSummaryResponse(BaseModel):
    source: str
    company_name: str
    job_name: str
    extracted_keywords: List[str]
    summary: str = ""
    email_generation_prompt: str = ""
    llm_used: bool
    llm_error: Optional[str] = None
