from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import csv
import json
import os
import re

import requests
from bs4 import BeautifulSoup


STOP_WORDS = {
    "the", "and", "for", "with", "you", "your", "are", "this", "that", "from",
    "our", "have", "will", "all", "job", "role", "team", "work", "about", "into",
    "who", "what", "when", "where", "why", "how", "their", "they", "them", "not",
    "but", "can", "should", "must", "required", "preferred", "years", "experience",
    "skills", "ability", "using", "use", "including", "plus", "need", "needs",
    "office", "onsite", "salary", "benefits", "insurance", "holiday", "vacation",
    "paid", "leave", "apply", "application", "equal", "employment", "opportunity",
    "veteran", "disability", "gender", "race", "ethnicity", "military", "status",
    "select", "form", "example", "request", "accommodation",
}

DEFAULT_TECH_PHRASES: Dict[str, str] = {
    "apache flink": "Flink",
    "flink": "Flink",
    "apache kafka": "Kafka",
    "kafka": "Kafka",
    "google data flow": "Google Data Flow",
    "google dataflow": "Google Data Flow",
    "dataflow": "Dataflow",
    "java": "Java",
    "python": "Python",
    "scala": "Scala",
    "sql": "SQL",
    "distributed computing": "Distributed Computing",
    "streaming pipelines": "Streaming Pipelines",
    "real-time data": "Real-Time Data",
    "low-latency": "Low-Latency",
    "checkpointing": "Checkpointing",
    "dynamic filtering": "Dynamic Filtering",
    "auto-healing": "Auto-Healing",
    "data quality": "Data Quality",
    "data governance": "Data Governance",
    "cloud platforms": "Cloud Platforms",
    "relational data modeling": "Relational Data Modeling",
    "streaming analytics": "Streaming Analytics",
    "monitoring": "Monitoring",
    "internal tooling": "Internal Tooling",
}

NOISE_CUT_MARKERS = [
    "voluntary self-identification",
    "equal employment opportunity",
    "eeo",
    "veteran status",
    "disability status",
    "race/ethnicity",
    "gender identity",
    "form cc-305",
]

ACRONYMS = {
    "api", "aws", "gcp", "sql", "etl", "elt", "nlp", "llm", "ml", "ai",
    "kpi", "sla", "slo", "sdk", "ci", "cd", "oauth", "grpc", "rest", "json",
    "xml", "ui", "ux", "db", "nosql", "olap", "oltp",
}

CSV_TERM_COLUMNS = ["skill", "technology", "name", "preferred_label", "label", "term"]


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _canonicalize_term(term: str) -> str:
    words = _normalize_space(term).split(" ")
    out = []
    for word in words:
        low = word.lower().strip()
        if low in ACRONYMS:
            out.append(low.upper())
        elif re.fullmatch(r"[A-Z0-9\-+/#.]+", word):
            out.append(word)
        else:
            out.append(word.capitalize())
    return " ".join(out)


def _clean_phrase(term: str) -> str:
    cleaned = re.sub(r"\s*\([^)]*\)", "", term)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ,.;:-")


def _add_phrase(mapping: Dict[str, str], raw_phrase: str, canonical: Optional[str] = None) -> None:
    phrase = _clean_phrase(raw_phrase)
    if len(phrase) < 2:
        return

    normalized_key = phrase.lower()
    canonical_value = canonical or _canonicalize_term(phrase)

    if normalized_key not in mapping:
        mapping[normalized_key] = canonical_value


def _split_compound(term: str) -> List[str]:
    parts = re.split(r"\s*(?:;|/|\||,| and )\s*", term, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


def _load_json_phrases(path: Path) -> Dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    mapping: Dict[str, str] = {}

    if isinstance(data, dict):
        for key, value in data.items():
            canonical = str(value).strip() if value else _canonicalize_term(str(key))
            _add_phrase(mapping, str(key), canonical)
    elif isinstance(data, list):
        for item in data:
            _add_phrase(mapping, str(item))

    return mapping


def _load_onet_txt_phrases(path: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}

    with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames:
            return mapping

        fieldnames = {name.lower(): name for name in reader.fieldnames}
        example_col = fieldnames.get("example")
        commodity_col = fieldnames.get("commodity title")
        hot_col = fieldnames.get("hot technology")

        if not example_col:
            return mapping

        for row in reader:
            hot_flag = (row.get(hot_col, "") if hot_col else "").strip().upper()
            if hot_col and hot_flag != "Y":
                continue

            example = (row.get(example_col) or "").strip()
            commodity = (row.get(commodity_col) or "").strip() if commodity_col else ""

            for piece in _split_compound(example):
                _add_phrase(mapping, piece)

            if commodity:
                _add_phrase(mapping, commodity)

    return mapping


def _load_csv_phrases(path: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return mapping

        lower_to_actual = {name.lower(): name for name in reader.fieldnames}
        target_col = None
        for candidate in CSV_TERM_COLUMNS:
            if candidate in lower_to_actual:
                target_col = lower_to_actual[candidate]
                break

        if not target_col:
            return mapping

        for row in reader:
            value = (row.get(target_col) or "").strip()
            if value:
                _add_phrase(mapping, value)
    return mapping


def _load_txt_phrases(path: Path) -> Dict[str, str]:
    first_line = path.read_text(encoding="utf-8", errors="ignore").splitlines()[:1]
    if first_line and "O*NET-SOC Code" in first_line[0] and "Example" in first_line[0]:
        return _load_onet_txt_phrases(path)

    mapping: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        _add_phrase(mapping, line)
    return mapping


def _taxonomy_paths_from_env_or_default() -> List[Path]:
    env_value = os.getenv("TECH_TAXONOMY_PATHS", "").strip()
    if env_value:
        return [Path(part.strip()) for part in env_value.split(",") if part.strip()]

    base = _backend_root() / "data" / "taxonomy"
    return [
        base / "tech_phrases.json",
        base / "tech_phrases.csv",
        base / "tech_phrases.txt",
        base / "onet_technology_skills.txt",
    ]


@lru_cache(maxsize=1)
def load_tech_phrase_map() -> Dict[str, str]:
    merged: Dict[str, str] = {}

    for alias, canonical in DEFAULT_TECH_PHRASES.items():
        _add_phrase(merged, alias, canonical)

    for path in _taxonomy_paths_from_env_or_default():
        if not path.exists() or not path.is_file():
            continue

        try:
            suffix = path.suffix.lower()
            if suffix == ".json":
                loaded = _load_json_phrases(path)
            elif suffix == ".csv":
                loaded = _load_csv_phrases(path)
            elif suffix == ".txt":
                loaded = _load_txt_phrases(path)
            else:
                continue

            for alias, canonical in loaded.items():
                if alias not in merged:
                    merged[alias] = canonical
        except Exception:
            # Keep service resilient; if one source is malformed, continue with others.
            continue

    return merged


def fetch_job_text_from_url(job_link: str, timeout_sec: int = 10) -> str:
    """
    Fetch human-readable text from a job posting URL.

    TODO(LLM): If page structure is complex, replace this with an LLM extraction
    strategy over page HTML to reliably isolate role/company/requirements.
    """
    response = requests.get(
        job_link,
        timeout=timeout_sec,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "noscript", "form", "input", "button", "select", "option", "label"]):
        tag.decompose()

    text = " ".join(soup.get_text(separator=" ").split())
    return text


def _remove_noise_sections(text: str) -> str:
    lowered = text.lower()
    cut_positions = [lowered.find(marker) for marker in NOISE_CUT_MARKERS if lowered.find(marker) > 0]
    if not cut_positions:
        return text
    return text[: min(cut_positions)].strip()


def _extract_tech_phrases(text: str) -> List[str]:
    lowered = text.lower()
    found: List[str] = []
    seen = set()

    for raw_phrase, canonical in load_tech_phrase_map().items():
        pattern = r"\b" + re.escape(raw_phrase) + r"\b"
        if re.search(pattern, lowered) and canonical.lower() not in seen:
            found.append(canonical)
            seen.add(canonical.lower())
    return found


def extract_keywords_from_text(text: str, top_k: int = 12) -> List[str]:
    """
    Extract representative keywords from job text.

    TODO(LLM): Replace with LLM-based or embedding-based keyphrase extraction.
    """
    cleaned_text = _remove_noise_sections(text)
    tech_matches = _extract_tech_phrases(cleaned_text)
    if len(tech_matches) >= top_k:
        return tech_matches[:top_k]

    candidates = re.findall(r"[A-Za-z][A-Za-z0-9+#\-/]{2,}", cleaned_text.lower())
    counts = {}
    for token in candidates:
        if token in STOP_WORDS or token.isdigit():
            continue
        counts[token] = counts.get(token, 0) + 1

    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    fallback = []
    tech_lower = {item.lower() for item in tech_matches}
    for word, _ in ranked:
        if word in STOP_WORDS:
            continue
        if word.lower() in tech_lower:
            continue
        fallback.append(word)
        if len(tech_matches) + len(fallback) >= top_k:
            break

    return tech_matches + fallback


def resolve_job_text_and_keywords(
    job_description: Optional[str],
    job_link: Optional[str],
) -> Tuple[str, List[str]]:
    """
    Resolve final job text for downstream parse/RAG plus extracted keywords.
    """
    if job_description and len(job_description.strip()) >= 20:
        final_text = job_description.strip()
    else:
        if not job_link:
            raise ValueError("Provide either a job description or a valid job link.")
        final_text = fetch_job_text_from_url(job_link)

    keywords = extract_keywords_from_text(final_text)
    return final_text, keywords
