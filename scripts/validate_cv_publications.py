#!/usr/bin/env python3
"""Validate CV publication entries against the BibTeX bibliography."""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CV = Path("_data/cv.yml")
DEFAULT_BIB = Path("_bibliography/papers.bib")

VENUE_ALIASES = {
    "international conference on learning representations": "iclr",
    "international conference on machine learning": "icml",
    "annual meeting of the association for computational linguistics": "acl",
    "conference of the european chapter of the association for computational linguistics": "eacl",
    "european conference on computer vision": "eccv",
    "ieee cvf conference on computer vision and pattern recognition": "cvpr",
    "winter conference on applications of computer vision": "wacv",
}


LATEX_ACCENTS = {
    r"\'": "",
    r"\`": "",
    r"\^": "",
    r'\"': "",
    r"\~": "",
    r"\c": "",
    r"\=": "",
    r"\.": "",
    r"\u": "",
    r"\v": "",
    r"\H": "",
    r"\r": "",
    r"\t": "",
    r"\b": "",
    r"\d": "",
}


def strip_latex(value: str) -> str:
    text = value
    for command, replacement in LATEX_ACCENTS.items():
        text = text.replace(command, replacement)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{([^{}]*)\})?", r"\1", text)
    text = text.replace("{", "").replace("}", "")
    return text


def normalize_text(value: str) -> str:
    text = strip_latex(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_title(value: str) -> str:
    return normalize_text(value)


def normalize_venue(value: str) -> str:
    text = normalize_text(re.sub(r"\([^)]*\)", "", value))
    text = text.replace(" oral", "")
    return VENUE_ALIASES.get(text, text)


def normalize_author_name(value: str) -> str:
    text = strip_latex(value).replace("*", "").strip()
    text = re.sub(r"\s+", " ", text)
    if "," in text:
        last, first = [part.strip() for part in text.split(",", 1)]
        text = f"{first} {last}".strip()
    return normalize_text(text)


def normalize_authors(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_authors = [str(author) for author in value]
    else:
        raw_authors = re.split(r"\s+and\s+", str(value))
    authors = []
    for author in raw_authors:
        normalized = normalize_author_name(author)
        if normalized in {"others", "et al"}:
            continue
        if normalized:
            authors.append(normalized)
    return authors


def extract_arxiv(value: Any) -> str:
    text = "" if value is None else str(value)
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^/?#]+)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).removesuffix(".pdf")
    return text.strip()


def bib_venue(entry: dict[str, str]) -> str:
    return entry.get("booktitle") or entry.get("journal") or entry.get("publisher") or ""


def extract_balanced_value(text: str, start: int) -> tuple[str, int]:
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text):
        return "", start

    opener = text[start]
    if opener == "{":
        depth = 1
        index = start + 1
        while index < len(text) and depth > 0:
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
            index += 1
        return text[start + 1 : index - 1], index

    if opener == '"':
        index = start + 1
        escaped = False
        while index < len(text):
            char = text[index]
            if char == '"' and not escaped:
                return text[start + 1 : index], index + 1
            escaped = char == "\\" and not escaped
            if char != "\\":
                escaped = False
            index += 1
        return text[start + 1 :], index

    match = re.match(r"([^,\n]+)", text[start:])
    if not match:
        return "", start
    return match.group(1).strip(), start + match.end()


def extract_bib_entry(text: str, start: int) -> tuple[str, int]:
    opener = text.find("{", start)
    if opener == -1:
        return "", start
    depth = 1
    index = opener + 1
    while index < len(text) and depth > 0:
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
        index += 1
    return text[opener + 1 : index - 1], index


def parse_bib_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    comma = body.find(",")
    if comma == -1:
        return fields
    index = comma + 1
    while index < len(body):
        match = re.search(r"([A-Za-z][A-Za-z0-9_-]*)\s*=", body[index:])
        if not match:
            break
        field = match.group(1).lower()
        value_start = index + match.end()
        value, value_end = extract_balanced_value(body, value_start)
        fields[field] = value.strip()
        index = value_end + 1
    return fields


def bib_entries(path: Path) -> dict[str, dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    entries: dict[str, dict[str, str]] = {}
    for match in re.finditer(r"@[A-Za-z]+\s*\{", text):
        body, _ = extract_bib_entry(text, match.end() - 1)
        fields = parse_bib_fields(body)
        if fields.get("title"):
            entries[normalize_title(fields["title"])] = fields
    return entries


def cv_publications(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sections = data.get("cv", {}).get("sections", {})
    publications = sections.get("Publications", [])
    return [entry for entry in publications if isinstance(entry, dict) and entry.get("title")]


def compare_required(cv_pub: dict[str, Any], bib_pub: dict[str, str]) -> list[str]:
    errors = []
    title = str(cv_pub.get("title", ""))
    if normalize_title(title) != normalize_title(bib_pub.get("title", "")):
        errors.append(f"title differs: CV={title!r}, BibTeX={bib_pub.get('title', '')!r}")

    cv_year = str(cv_pub.get("releaseDate", "")).strip()
    bib_year = str(bib_pub.get("year", "")).strip()
    if cv_year != bib_year:
        errors.append(f"year differs for {title!r}: CV={cv_year!r}, BibTeX={bib_year!r}")

    cv_arxiv = extract_arxiv(cv_pub.get("url", ""))
    bib_arxiv = extract_arxiv(bib_pub.get("arxiv", ""))
    if cv_arxiv != bib_arxiv:
        errors.append(f"arXiv differs for {title!r}: CV={cv_arxiv!r}, BibTeX={bib_arxiv!r}")
    return errors


def compare_curated_fields(cv_pub: dict[str, Any], bib_pub: dict[str, str]) -> list[str]:
    errors = []
    title = str(cv_pub.get("title", ""))

    cv_venue = normalize_venue(str(cv_pub.get("publisher", "")))
    bib_pub_venue = normalize_venue(bib_venue(bib_pub))
    if cv_venue and bib_pub_venue and cv_venue != bib_pub_venue:
        errors.append(f"venue differs for {title!r}: CV={cv_pub.get('publisher', '')!r}, BibTeX={bib_venue(bib_pub)!r}")

    cv_authors = normalize_authors(cv_pub.get("authors", []))
    bib_authors = normalize_authors(bib_pub.get("author", ""))
    if cv_authors and bib_authors and cv_authors != bib_authors:
        errors.append(f"authors differ for {title!r}")

    cv_summary = normalize_text(str(cv_pub.get("summary", "")))
    bib_abstract = normalize_text(bib_pub.get("abstract", ""))
    if cv_summary and bib_abstract and cv_summary != bib_abstract:
        errors.append(f"summary/abstract differs for {title!r}")
    return errors


def validate(cv_path: Path, bib_path: Path) -> int:
    pubs = cv_publications(cv_path)
    bibliography = bib_entries(bib_path)
    errors = []

    for pub in pubs:
        title = str(pub["title"])
        bib_pub = bibliography.get(normalize_title(title))
        if not bib_pub:
            errors.append(f"missing from bibliography: {title}")
            continue
        errors.extend(compare_required(pub, bib_pub))
        errors.extend(compare_curated_fields(pub, bib_pub))

    print(f"CV publications: {len(pubs)}")
    print(f"BibTeX titles: {len(bibliography)}")

    if errors:
        print("Errors:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("OK: CV publication fields match the bibliography.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate CV publication titles against BibTeX.")
    parser.add_argument("--cv", type=Path, default=DEFAULT_CV)
    parser.add_argument("--bib", type=Path, default=DEFAULT_BIB)
    args = parser.parse_args()
    raise SystemExit(validate(args.cv, args.bib))


if __name__ == "__main__":
    main()
