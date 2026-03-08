from pydantic import BaseModel, EmailStr, Field
from typing import List


class JobOutreachRequest(BaseModel):
    job_description: str = Field(..., min_length=20)
    recruiter_name: str = Field(..., min_length=2)
    recruiter_email: EmailStr
    recruiter_profile: str = Field(..., min_length=20)
    resume_text: str = Field(..., min_length=50)


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


class SendEmailResponse(BaseModel):
    status: str
    message: str
