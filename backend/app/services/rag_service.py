from typing import List
from app.schemas import EvidenceItem


def chunk_resume(resume_text: str, chunk_size: int = 350) -> List[str]:
    words = resume_text.split()
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunks.append(" ".join(words[i : i + chunk_size]))
    return chunks


def retrieve_resume_evidence(query: str, resume_text: str, top_k: int = 4) -> List[EvidenceItem]:
    """
    Retrieve the most relevant resume snippets for a given query.

    TODO(RAG): Replace this placeholder with your real RAG pipeline:
    1) Embed chunks with Sentence-BERT (e.g., all-MiniLM-L6-v2)
    2) Build/search a FAISS index
    3) Return top_k nearest chunks with true similarity scores
    """
    chunks = chunk_resume(resume_text)

    # Placeholder ranking: naive keyword overlap scoring
    query_terms = {t.lower() for t in query.split() if len(t) > 2}
    scored = []

    for chunk in chunks:
        chunk_terms = {t.lower().strip(".,:;()[]") for t in chunk.split()}
        overlap = len(query_terms.intersection(chunk_terms))
        score = overlap / max(len(query_terms), 1)
        scored.append((chunk, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:top_k]

    return [
        EvidenceItem(snippet=snippet[:600], relevance_score=round(score, 3))
        for snippet, score in top
    ]
