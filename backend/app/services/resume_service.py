from io import BytesIO
from typing import Optional

from fastapi import HTTPException, UploadFile
from pypdf import PdfReader
from docx import Document


def extract_resume_text_from_upload(resume_file: UploadFile) -> str:
    filename = (resume_file.filename or "resume").lower()
    content = resume_file.file.read()

    if not content:
        raise HTTPException(status_code=400, detail="Uploaded resume file is empty.")

    if filename.endswith(".txt"):
        try:
            return content.decode("utf-8", errors="ignore").strip()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Failed to read TXT resume: {exc}")

    if filename.endswith(".pdf"):
        try:
            reader = PdfReader(BytesIO(content))
            text_parts = []
            for page in reader.pages:
                text_parts.append(page.extract_text() or "")
            return "\n".join(text_parts).strip()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Failed to read PDF resume: {exc}")

    if filename.endswith(".docx"):
        try:
            doc = Document(BytesIO(content))
            return "\n".join(p.text for p in doc.paragraphs).strip()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Failed to read DOCX resume: {exc}")

    raise HTTPException(
        status_code=400,
        detail="Unsupported resume format. Use .txt, .pdf, or .docx",
    )


def resolve_resume_text(
    resume_text: Optional[str],
    resume_file: Optional[UploadFile],
) -> str:
    if resume_text and len(resume_text.strip()) >= 50:
        return resume_text.strip()

    if resume_file is not None:
        extracted = extract_resume_text_from_upload(resume_file)
        if len(extracted) < 50:
            raise HTTPException(
                status_code=400,
                detail="Resume content is too short after extraction. Provide a fuller resume.",
            )
        return extracted

    raise HTTPException(
        status_code=400,
        detail="Provide resume_text (>=50 chars) or upload a resume file.",
    )
