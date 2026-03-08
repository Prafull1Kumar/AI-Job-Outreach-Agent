#!/usr/bin/env python3
"""
Download O*NET Technology Skills and prepare local taxonomy files.

Usage:
  python scripts/fetch_onet_tech_skills.py
"""

from pathlib import Path
import csv
import json
import requests

ONET_URL = "https://www.onetcenter.org/dl_files/database/db_27_0_text/Technology%20Skills.txt"


def canonicalize(term: str) -> str:
    return " ".join(part.capitalize() for part in term.strip().split())


def main() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    out_dir = backend_dir / "data" / "taxonomy"
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_path = out_dir / "onet_technology_skills.txt"
    json_path = out_dir / "tech_phrases.json"

    print(f"Downloading: {ONET_URL}")
    response = requests.get(ONET_URL, timeout=30)
    response.raise_for_status()
    raw_path.write_text(response.text, encoding="utf-8")
    print(f"Saved raw file: {raw_path}")

    phrases = {}
    with raw_path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            hot_flag = (row.get("Hot Technology", "") or "").strip().upper()
            if hot_flag != "Y":
                continue

            for col in ["Example", "Commodity Title"]:
                value = (row.get(col, "") or "").strip()
                if not value:
                    continue
                norm = value.lower()
                if norm not in phrases:
                    phrases[norm] = canonicalize(value)

    json_path.write_text(json.dumps(phrases, indent=2), encoding="utf-8")
    print(f"Saved extracted JSON phrases: {json_path}")
    print(f"Loaded phrase count: {len(phrases)}")


if __name__ == "__main__":
    main()
