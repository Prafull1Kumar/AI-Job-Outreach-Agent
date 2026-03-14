from functools import lru_cache
from html import unescape
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
    return _extract_all_text_from_html(fetch_job_html_from_url(job_link, timeout_sec=timeout_sec))


def fetch_job_html_from_url(job_link: str, timeout_sec: int = 10) -> str:
    response = requests.get(
        job_link,
        timeout=timeout_sec,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    response.raise_for_status()
    return response.text


def _html_fragment_to_text(fragment: str) -> str:
    parsed = BeautifulSoup(unescape(fragment), "html.parser")
    return _normalize_space(parsed.get_text(separator=" "))


def _collect_text_from_json_value(value: object, texts: List[str]) -> None:
    if isinstance(value, str):
        normalized = _html_fragment_to_text(value)
        if normalized:
            texts.append(normalized)
        return

    if isinstance(value, list):
        for item in value:
            _collect_text_from_json_value(item, texts)
        return

    if isinstance(value, dict):
        for item in value.values():
            _collect_text_from_json_value(item, texts)


def _extract_structured_job_text(soup: BeautifulSoup) -> str:
    texts: List[str] = []

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue

        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("@type", "")).lower()
            if item_type != "jobposting":
                continue

            title = str(item.get("title", "")).strip()
            description = _html_fragment_to_text(str(item.get("description", "")))
            if title:
                texts.append(title)
            if description:
                texts.append(description)

    for meta_name in ["description", "og:description", "twitter:description"]:
        meta = soup.find("meta", attrs={"name": meta_name}) or soup.find("meta", attrs={"property": meta_name})
        if meta and meta.get("content"):
            texts.append(_normalize_space(str(meta["content"])))

    combined = _normalize_space(" ".join(part for part in texts if part))
    return combined


def _extract_all_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    texts: List[str] = []

    for meta in soup.find_all("meta"):
        content = meta.get("content")
        if content:
            texts.append(_html_fragment_to_text(str(content)))

    for script in soup.find_all("script"):
        script_text = script.string or script.get_text()
        if script_text:
            script_type = (script.get("type") or "").lower()
            if "json" in script_type:
                try:
                    payload = json.loads(script_text)
                except json.JSONDecodeError:
                    cleaned_script = _html_fragment_to_text(script_text)
                    if cleaned_script:
                        texts.append(cleaned_script)
                else:
                    _collect_text_from_json_value(payload, texts)

    for node in soup.find_all(string=True):
        value = _normalize_space(str(node))
        if value:
            texts.append(value)

    combined = _normalize_space(" ".join(texts))
    return combined


def _remove_noise_sections(text: str) -> str:
    lowered = text.lower()
    cut_positions = [lowered.find(marker) for marker in NOISE_CUT_MARKERS if lowered.find(marker) > 0]
    if not cut_positions:
        return text
    return text[: min(cut_positions)].strip()


def _remove_stop_words_from_text(text: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9+#\-/\.]+|[^\w\s]", text)
    filtered_tokens = []
    for token in tokens:
        normalized = token.lower().strip(".,;:!?()[]{}\"'")
        if normalized and normalized in STOP_WORDS:
            continue
        filtered_tokens.append(token)

    filtered_text = " ".join(filtered_tokens)
    filtered_text = re.sub(r"\s+([,.;:!?])", r"\1", filtered_text)
    return _normalize_space(filtered_text)


def _prepare_extracted_job_text(text: str) -> str:
    noise_reduced = _remove_noise_sections(text)
    return _remove_stop_words_from_text(noise_reduced)


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
    cleaned_text = _prepare_extracted_job_text(text)
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


def resolve_job_summary_input(
    job_description: Optional[str],
    job_link: Optional[str],
) -> str:
    """
    Resolve source text for summarization.

    For job links, this intentionally returns the raw HTML page source so the
    LLM can summarize from the full document instead of flattened extraction.
    """
    if job_description and len(job_description.strip()) >= 20:
        return job_description.strip()
    if not job_link:
        raise ValueError("Provide either a job description or a valid job link.")
    return fetch_job_html_from_url(job_link)
