import re
from typing import Dict, List, Tuple

from app.schemas import EvidenceItem
import faiss
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

try:
    from unstructured.chunking.title import chunk_by_title
    from unstructured.partition.text import partition_text
except Exception:  # pragma: no cover - optional dependency fallback
    chunk_by_title = None
    partition_text = None



_EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
_embedding_model = None


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def chunk_resume(resume_text: str, chunk_size: int = 160, overlap: int = 40) -> List[str]:
    structured_chunks = _chunk_resume_with_unstructured(resume_text)
    if structured_chunks:
        return structured_chunks

    return _chunk_resume_fallback(resume_text, chunk_size=chunk_size, overlap=overlap)


def _chunk_resume_with_unstructured(resume_text: str) -> List[str]:
    if chunk_by_title is None or partition_text is None:
        return _chunk_resume_by_sections(resume_text)

    cleaned = _normalize_space(resume_text)
    if not cleaned:
        return []

    elements = partition_text(text=resume_text)
    if not elements:
        return []

    chunked_elements = chunk_by_title(
        elements,
        max_characters=1100,
        new_after_n_chars=900,
        combine_text_under_n_chars=250,
        overlap=80,
    )

    chunks: List[str] = []
    for element in chunked_elements:
        text = _normalize_space(str(element))
        if text:
            chunks.append(text)

    return _dedupe_chunks(chunks)


def _chunk_resume_by_sections(resume_text: str) -> List[str]:
    blocks = re.split(r"\n\s*\n+", resume_text)
    normalized_blocks = [_normalize_space(block) for block in blocks if _normalize_space(block)]

    chunks: List[str] = []
    buffer = ""
    for block in normalized_blocks:
        candidate = f"{buffer}\n\n{block}".strip() if buffer else block
        if len(candidate) <= 1100:
            buffer = candidate
            continue

        if buffer:
            chunks.append(buffer)
        buffer = block

    if buffer:
        chunks.append(buffer)

    if chunks:
        return _dedupe_chunks(chunks)

    return _chunk_resume_fallback(resume_text)


def _chunk_resume_fallback(resume_text: str, chunk_size: int = 160, overlap: int = 40) -> List[str]:
    words = resume_text.split()
    if not words:
        return []

    step = max(chunk_size - overlap, 1)
    chunks: List[str] = []
    for start in range(0, len(words), step):
        chunk = " ".join(words[start : start + chunk_size]).strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_size >= len(words):
            break
    return _dedupe_chunks(chunks)


def _dedupe_chunks(chunks: List[str]) -> List[str]:
    unique: List[str] = []
    seen = set()
    for chunk in chunks:
        key = chunk.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(chunk)
    return unique


def retrieve_resume_evidence(query: str, resume_text: str, top_k: int = 4) -> List[EvidenceItem]:
    chunks = chunk_resume(resume_text)
    if not chunks:
        return []

    try:
        return _hybrid_retrieve(query, chunks, top_k=top_k)
    except Exception:
        return _keyword_overlap_fallback(query, chunks, top_k=top_k)


def _hybrid_retrieve(query: str, chunks: List[str], top_k: int) -> List[EvidenceItem]:
    if not SentenceTransformer or not np or not faiss or not BM25Okapi:
        raise RuntimeError("Hybrid retrieval dependencies are not installed.")

    model = _get_embedding_model()
    dense_hits = _dense_search(model, query, chunks, top_k=max(top_k * 3, 8))
    sparse_hits = _sparse_search(query, chunks, top_k=max(top_k * 3, 8))
    fused = _reciprocal_rank_fusion(dense_hits, sparse_hits, k=60)

    best = fused[:top_k]
    max_score = best[0][1] if best else 1.0
    if max_score <= 0:
        max_score = 1.0

    return [
        EvidenceItem(
            snippet=_normalize_space(chunks[idx])[:700],
            relevance_score=round(score / max_score, 3),
        )
        for idx, score in best
    ]


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(_EMBED_MODEL_NAME)
    return _embedding_model


def _dense_search(model, query: str, chunks: List[str], top_k: int) -> List[Tuple[int, float]]:
    chunk_vectors = model.encode(chunks, convert_to_numpy=True, normalize_embeddings=True)
    query_vector = model.encode([query], convert_to_numpy=True, normalize_embeddings=True)

    chunk_vectors = np.asarray(chunk_vectors, dtype="float32")
    query_vector = np.asarray(query_vector, dtype="float32")

    index = faiss.IndexFlatIP(chunk_vectors.shape[1])
    index.add(chunk_vectors)
    scores, indices = index.search(query_vector, min(top_k, len(chunks)))

    hits: List[Tuple[int, float]] = []
    for idx, score in zip(indices[0], scores[0]):
        if idx < 0:
            continue
        hits.append((int(idx), float(score)))
    return hits


def _sparse_search(query: str, chunks: List[str], top_k: int) -> List[Tuple[int, float]]:
    tokenized_chunks = [_tokenize_for_bm25(chunk) for chunk in chunks]
    bm25 = BM25Okapi(tokenized_chunks)
    scores = bm25.get_scores(_tokenize_for_bm25(query))

    ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
    return [(idx, float(score)) for idx, score in ranked[: min(top_k, len(ranked))]]


def _tokenize_for_bm25(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9+#.\-/]+", text.lower())


def _reciprocal_rank_fusion(
    dense_hits: List[Tuple[int, float]],
    sparse_hits: List[Tuple[int, float]],
    k: int = 60,
) -> List[Tuple[int, float]]:
    fused: Dict[int, float] = {}

    for rank, (idx, _) in enumerate(dense_hits, start=1):
        fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank)

    for rank, (idx, _) in enumerate(sparse_hits, start=1):
        fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank)

    return sorted(fused.items(), key=lambda item: item[1], reverse=True)


def _keyword_overlap_fallback(query: str, chunks: List[str], top_k: int) -> List[EvidenceItem]:
    query_terms = {t.lower() for t in _tokenize_for_bm25(query) if len(t) > 2}
    scored = []

    for chunk in chunks:
        chunk_terms = set(_tokenize_for_bm25(chunk))
        overlap = len(query_terms.intersection(chunk_terms))
        coverage = overlap / max(len(query_terms), 1)
        length_penalty = min(len(chunk_terms) / 120.0, 1.0)
        score = coverage * 0.85 + length_penalty * 0.15
        scored.append((chunk, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    top = scored[:top_k]

    return [
        EvidenceItem(snippet=_normalize_space(snippet)[:700], relevance_score=round(score, 3))
        for snippet, score in top
    ]
