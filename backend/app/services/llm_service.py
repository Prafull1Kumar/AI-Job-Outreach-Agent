from app.schemas import DraftEmailResponse, EvidenceItem, ParsedJob
from typing import List
import re


def parse_job_description(job_description: str) -> ParsedJob:
    """
    Parse role/company/requirements from JD.

    TODO(LLM): Replace heuristics with an LLM structured extraction call.
    Suggested output schema: {role, company, key_requirements[], seniority}
    """
    lines = [line.strip() for line in job_description.splitlines() if line.strip()]
    role = lines[0] if lines else "Unknown Role"

    company_match = re.search(r"at\s+([A-Z][A-Za-z0-9&\-\s]+)", job_description)
    company = company_match.group(1).strip() if company_match else "Target Company"

    req_keywords = [
        "python",
        "llm",
        "rag",
        "fastapi",
        "api",
        "machine learning",
        "nlp",
        "faiss",
        "embeddings",
    ]
    key_requirements = [k for k in req_keywords if k in job_description.lower()]

    seniority = "Mid/Senior" if "senior" in job_description.lower() else "Mid"

    return ParsedJob(
        role=role,
        company=company,
        key_requirements=key_requirements or ["Strong relevant technical background"],
        seniority=seniority,
    )


def draft_outreach_email(
    recruiter_name: str,
    recruiter_profile: str,
    parsed_job: ParsedJob,
    evidence: List[EvidenceItem],
) -> DraftEmailResponse:
    """
    Draft personalized recruiter outreach email.

    TODO(LLM): Replace this template generator with an LLM call using:
    - recruiter profile
    - parsed job JSON
    - retrieved resume evidence
    - strict style constraints (concise, professional, personalized)
    """
    evidence_lines = "\n".join(
        [f"- {item.snippet[:140]}..." for item in evidence[:3]]
    )

    subject = f"Interest in {parsed_job.role} - Relevant LLM/RAG Experience"

    body = f"""Hi {recruiter_name},

I came across the {parsed_job.role} opportunity at {parsed_job.company} and wanted to reach out directly.
Your background ({recruiter_profile[:120]}...) stood out, and I believe my recent work aligns strongly with this role.

Highlights from my experience relevant to your requirements:
{evidence_lines}

I recently built an AI Job Outreach Agent using FastAPI, LLM workflows, and retrieval-based grounding, and would value the chance to discuss how I can contribute to your team.

Would you be open to a short conversation this week?

Best regards,
Your Name
"""

    return DraftEmailResponse(subject=subject, body=body, evidence_used=evidence)
