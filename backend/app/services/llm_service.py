import json
import os
import re
from html import unescape
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from app.schemas import DraftEmailResponse, EvidenceItem, JobSummaryResponse, ParsedJob


def parse_job_description(
    job_description: str,
    extracted_keywords: Optional[List[str]] = None,
) -> ParsedJob:
    """
    Parse role/company/requirements from JD.

    TODO(LLM): Replace heuristics with an LLM structured extraction call.
    Suggested output schema: {role, company, key_requirements[], seniority}
    """
    role, company = _extract_role_and_company(job_description)

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
    if extracted_keywords:
        for keyword in extracted_keywords:
            if keyword not in key_requirements:
                key_requirements.append(keyword)
            if len(key_requirements) >= 10:
                break

    seniority = "Mid/Senior" if "senior" in job_description.lower() else "Mid"

    return ParsedJob(
        role=role,
        company=company,
        key_requirements=key_requirements or ["Strong relevant technical background"],
        seniority=seniority,
    )


def _extract_role_and_company(job_description: str) -> tuple[str, str]:
    normalized = re.sub(r"\s+", " ", job_description).strip()

    patterns = [
        r"Job Application for\s+(?P<role>.+?)\s+at\s+(?P<company>[A-Z][A-Za-z0-9&.\- ]+)",
        r"(?P<role>[A-Z][A-Za-z0-9/&,\-+() ]+?)\s*@\s*(?P<company>[A-Z][A-Za-z0-9&.\- ]+)",
        r"(?P<role>[A-Z][A-Za-z0-9/&,\-+() ]+?)\s+-\s+(?P<company>[A-Z][A-Za-z0-9&.\- ]+)",
        r"(?P<role>[A-Z][A-Za-z0-9/&,\-+() ]+?)\s+at\s+(?P<company>[A-Z][A-Za-z0-9&.\- ]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            role = _clean_title_fragment(match.group("role"))
            company = _clean_title_fragment(match.group("company"))
            if role and company:
                return role, company

    lines = [line.strip() for line in job_description.splitlines() if line.strip()]
    first_line = _clean_title_fragment(lines[0]) if lines else ""
    fallback_role = first_line or "Software Engineer"
    return fallback_role, "Target Company"


def _clean_title_fragment(value: str) -> str:
    cleaned = value.strip()
    cleaned = re.sub(r"^(width=device-width.*?|viewport.*?)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:[A-Za-z0-9_-]{20,}\s+)+", "", cleaned)
    cleaned = re.sub(r"\s*(COMPANY DESCRIPTION|ROLE DESCRIPTION|REQUIREMENTS).*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" -,:;|")


def draft_outreach_email(
    recruiter_name: str,
    recruiter_profile: str,
    parsed_job: ParsedJob,
    evidence: List[EvidenceItem],
    job_summary_prompt: Optional[str] = None,
) -> DraftEmailResponse:
    """
    Draft personalized recruiter outreach email.

    TODO(LLM): Replace this template generator with an LLM call using:
    - recruiter profile
    - parsed job JSON
    - retrieved resume evidence
    - strict style constraints (concise, professional, personalized)
    """
    subject, body = _build_dummy_outreach_email(
        recruiter_name=recruiter_name,
        recruiter_profile=recruiter_profile,
        parsed_job=parsed_job,
    )

    return DraftEmailResponse(
        subject=subject,
        body=body,
        evidence_used=evidence,
        job_summary_prompt=job_summary_prompt,
    )


def _build_dummy_outreach_email(
    recruiter_name: str,
    recruiter_profile: str,
    parsed_job: ParsedJob,
) -> tuple[str, str]:
    greeting = recruiter_name.strip() if recruiter_name.strip() else "Hiring Team"
    profile_hint = recruiter_profile[:120].strip()
    company = parsed_job.company.strip() if parsed_job.company.strip() else "your team"
    intro_line = (
        f"I recently came across the {parsed_job.role} opportunity at {company} and was excited to learn more "
        "about your mission and the impact of your engineering team."
    )
    if profile_hint:
        intro_line += f" Your background ({profile_hint}...) also stood out to me."

    subject = f"Application for {parsed_job.role} Role at {company}"
    body = f"""Hi {greeting},

I hope you are doing well.

{intro_line} The opportunity to contribute to scalable, reliable systems in this role is especially compelling.

I have 5+ years of experience building scalable backend and full-stack applications, working with technologies such as Python, Node.js, React, TypeScript, APIs, distributed systems, and cloud-based workflows. In my recent roles and projects, I have built AI-powered systems, high-volume application workflows, data pipelines, and external integrations. I am currently pursuing my Master's in Computer Science at The University of Texas at Dallas, where I continue working on AI-driven and distributed systems projects.

I would welcome the opportunity to contribute to {company}. My resume is attached, and I would be glad to discuss how my background could be a strong fit for the team.

Thank you for your time and consideration.

Best regards,
Prafull Kumar Prajapati
Richardson, TX
prajapatiprafull12@gmail.com
+1 (945) 268-5954
"""

    return subject, body


def summarize_job_for_email_prompt(
    job_text: str,
    extracted_keywords: Optional[List[str]] = None,
) -> JobSummaryResponse:
    summary_input = _prepare_job_summary_input(job_text)
    summary, prompt, source, llm_used, llm_error = _summarize_job_with_optional_llm(
        summary_input,
        extracted_keywords or [],
    )
    return JobSummaryResponse(
        source=source,
        extracted_keywords=extracted_keywords or [],
        summary=summary,
        email_generation_prompt=prompt,
        llm_used=llm_used,
        llm_error=llm_error,
    )


def _summarize_job_with_optional_llm(
    job_text: str,
    extracted_keywords: List[str],
) -> tuple[str, str, str, bool, Optional[str]]:
    ollama_model = os.getenv("OLLAMA_MODEL", "").strip()
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    errors: List[str] = []

    if ollama_model:
        try:
            summary, prompt, llm_used = _summarize_job_with_ollama(
                job_text,
                extracted_keywords,
                ollama_base_url,
                ollama_model,
            )
            return summary, prompt, "ollama", llm_used, None
        except Exception as exc:
            errors.append(f"Ollama: {exc}")

    if api_key:
        try:
            summary, prompt, llm_used = _summarize_job_with_openai(job_text, extracted_keywords, api_key, model)
            return summary, prompt, "openai", llm_used, None
        except Exception as exc:
            errors.append(f"OpenAI: {exc}")

    summary, prompt, llm_used = _fallback_job_summary(job_text, extracted_keywords)
    if not ollama_model and not api_key:
        errors.append("No LLM provider configured. Set OLLAMA_MODEL or OPENAI_API_KEY.")
    return summary, prompt, "fallback", llm_used, " | ".join(errors) if errors else None


def _summarize_job_with_openai(
    job_text: str,
    extracted_keywords: List[str],
    api_key: str,
    model: str,
) -> tuple[str, str, bool]:
    system_prompt = (
        "You summarize job postings for outreach-email generation. "
        "Return strict JSON with keys: summary, email_generation_prompt. "
        "The summary must be concise, well-structured, and only include real job-relevant information. "
        "The email_generation_prompt must be a clean prompt that another model can use to draft a personalized outreach email. "
        "If the input contains HTML or scraped page content, ignore scripts, tracking, navigation, legal boilerplate, and application-form fields. "
        "Prioritize actual job title, responsibilities, requirements, technologies, team context, and company context. "
        "Do not repeat sections. Do not include raw HTML, metadata labels, or application form content."
    )
    user_prompt = {
        "job_text": job_text[:24000],
        "extracted_keywords": extracted_keywords,
        "instructions": {
            "summary_format": [
                "Company Overview",
                "Role Overview",
                "Key Responsibilities",
                "Requirements",
                "Engineering Culture & Benefits",
            ],
            "summary_style": (
                "Write a clean recruiter-style summary using the exact section headers above. "
                "Each section should be short and factual. "
                "Use bullets only for responsibilities and requirements when helpful. "
                "Focus on technologies, product area, scope, and candidate expectations."
            ),
            "email_generation_prompt": (
                "Write a prompt for generating a professional recruiter outreach email. "
                "Include role, company context if available, important technologies, key responsibilities, "
                "candidate alignment needs, and tone constraints. "
                "The prompt should tell the email-writing model to use the structured summary sections."
            ),
        },
    }

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_prompt)},
            ],
        },
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    parsed = _parse_llm_json_response(content)
    summary = str(parsed.get("summary", "")).strip()
    email_generation_prompt = str(parsed.get("email_generation_prompt", "")).strip()

    if not summary or not email_generation_prompt:
        raise ValueError("LLM response missing summary or email_generation_prompt")

    return summary, email_generation_prompt, True


def _summarize_job_with_ollama(
    job_text: str,
    extracted_keywords: List[str],
    base_url: str,
    model: str,
) -> tuple[str, str, bool]:
    compact_job_text = _truncate_for_local_model(job_text)
    timeout_seconds = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180"))
    system_prompt = (
        "You summarize job postings for outreach-email generation. "
        "Return strict JSON with keys: summary, email_generation_prompt. "
        "The summary must use these exact section headers: Company Overview, Role Overview, "
        "Key Responsibilities, Requirements, Engineering Culture & Benefits. "
        "Ignore scripts, tracking, legal boilerplate, and application form content."
    )
    user_prompt = {
        "job_text": compact_job_text,
        "extracted_keywords": extracted_keywords,
        "instructions": {
            "summary_style": (
                "Keep it factual and concise. Focus on role, technologies, responsibilities, "
                "requirements, and relevant benefits/culture."
            ),
            "email_generation_prompt": (
                "Write a prompt for generating a professional recruiter outreach email using the summary."
            ),
        },
    }

    response = requests.post(
        f"{base_url.rstrip('/')}/api/generate",
        json={
            "model": model,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.2,
                "num_predict": 450,
            },
            "system": system_prompt,
            "prompt": json.dumps(user_prompt),
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload.get("response", "")
    parsed = _parse_llm_json_response(content)

    summary = str(parsed.get("summary", "")).strip()
    email_generation_prompt = str(parsed.get("email_generation_prompt", "")).strip()
    if not summary or not email_generation_prompt:
        raise ValueError("Ollama response missing summary or email_generation_prompt")

    return summary, email_generation_prompt, True


def _fallback_job_summary(job_text: str, extracted_keywords: List[str]) -> tuple[str, str, bool]:
    normalized_text = re.sub(r"\s+", " ", job_text).strip()
    sentences = re.split(r"(?<=[.!?])\s+", normalized_text)
    selected_sentences = [sentence.strip() for sentence in sentences if sentence.strip()][:4]
    summary = " ".join(selected_sentences)[:1200]

    keyword_text = ", ".join(extracted_keywords[:15]) if extracted_keywords else "Not reliably extracted"
    prompt = (
        "Draft a concise, professional recruiter outreach email.\n"
        "Use the following job summary to personalize the email.\n\n"
        f"Job summary:\n{summary}\n\n"
        f"Important technologies and skills:\n{keyword_text}\n\n"
        "Email requirements:\n"
        "- Mention clear alignment with the role.\n"
        "- Reference the most relevant technologies and responsibilities.\n"
        "- Keep the tone direct, professional, and personalized.\n"
        "- Keep the email under 180 words.\n"
        "- End with a short call to action."
    )
    return summary, prompt, False


def _parse_llm_json_response(content: str) -> dict:
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    extracted = _extract_first_json_object(content)
    if extracted:
        try:
            parsed = json.loads(extracted)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    repaired = _recover_summary_fields(content)
    if repaired:
        return repaired

    raise ValueError("Model response was not valid JSON")


def _extract_first_json_object(content: str) -> Optional[str]:
    start = content.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(content)):
        ch = content[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return content[start : idx + 1]

    return None


def _recover_summary_fields(content: str) -> Optional[dict]:
    summary = _extract_field_block(content, "summary", "email_generation_prompt")
    prompt = _extract_field_block(content, "email_generation_prompt", None)

    if not summary and not prompt:
        return None

    return {
        "summary": summary or "",
        "email_generation_prompt": prompt or "",
    }


def _extract_field_block(content: str, field_name: str, next_field_name: Optional[str]) -> str:
    pattern = rf'"{re.escape(field_name)}"\s*:\s*"'
    match = re.search(pattern, content)
    if not match:
        return ""

    start = match.end()
    if next_field_name:
        next_pattern = rf'"\s*,\s*"{re.escape(next_field_name)}"\s*:'
        next_match = re.search(next_pattern, content[start:])
        if next_match:
            raw_value = content[start : start + next_match.start()]
        else:
            raw_value = content[start:]
    else:
        end_match = re.search(r'"\s*}\s*$', content[start:])
        raw_value = content[start : start + end_match.start()] if end_match else content[start:]

    cleaned = raw_value.strip().rstrip('",')
    cleaned = cleaned.replace('\\"', '"')
    cleaned = cleaned.replace("\\n", "\n")
    cleaned = cleaned.replace("\\t", "\t")
    cleaned = cleaned.replace("\\r", "")
    return cleaned.strip()


def _prepare_job_summary_input(job_text: str) -> str:
    if "<html" in job_text.lower() or "<body" in job_text.lower() or "<script" in job_text.lower():
        return _extract_job_relevant_text_from_html(job_text)
    return job_text


def _extract_job_relevant_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    texts: List[str] = []

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if title:
        texts.append(title)

    for meta_name in ["description", "og:description", "twitter:description"]:
        meta = soup.find("meta", attrs={"name": meta_name}) or soup.find("meta", attrs={"property": meta_name})
        if meta and meta.get("content"):
            texts.append(_html_to_text(str(meta["content"])))

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        _collect_job_json_text(payload, texts)

    for tag in soup(["script", "style", "noscript", "svg", "img"]):
        tag.decompose()

    body_text = soup.get_text(separator=" ")
    body_text = re.sub(r"\s+", " ", body_text).strip()
    if body_text:
        texts.append(body_text)

    deduped = []
    seen = set()
    for text in texts:
        cleaned = text.strip()
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            continue
        deduped.append(cleaned)
        seen.add(lowered)

    combined = "\n\n".join(deduped)
    return combined[:30000]


def _collect_job_json_text(value: object, texts: List[str]) -> None:
    if isinstance(value, dict):
        item_type = str(value.get("@type", "")).lower()
        priority_keys = [
            "title",
            "description",
            "qualifications",
            "responsibilities",
            "skills",
            "experienceRequirements",
            "hiringOrganization",
        ]
        if item_type == "jobposting":
            for key in priority_keys:
                if key in value:
                    _collect_job_json_text(value[key], texts)
            return
        for nested in value.values():
            _collect_job_json_text(nested, texts)
        return

    if isinstance(value, list):
        for item in value:
            _collect_job_json_text(item, texts)
        return

    if isinstance(value, str):
        cleaned = _html_to_text(value)
        if cleaned:
            texts.append(cleaned)


def _html_to_text(value: str) -> str:
    parsed = BeautifulSoup(unescape(value), "html.parser")
    return re.sub(r"\s+", " ", parsed.get_text(separator=" ")).strip()


def _truncate_for_local_model(job_text: str) -> str:
    normalized = re.sub(r"\s+", " ", job_text).strip()
    section_markers = [
        "Company Description",
        "About",
        "Role Description",
        "What You'll Do",
        "Responsibilities",
        "Requirements",
        "Qualifications",
        "Nice to Have",
        "Benefits",
    ]

    selected_parts: List[str] = []
    lowered = normalized.lower()
    for marker in section_markers:
        idx = lowered.find(marker.lower())
        if idx >= 0:
            selected_parts.append(normalized[idx : idx + 1600])

    if not selected_parts:
        selected_parts.append(normalized[:3500])

    compact = "\n\n".join(selected_parts)
    return compact[:4500]
