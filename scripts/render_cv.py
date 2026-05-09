#!/usr/bin/env python3
"""
Render a LaTeX/PDF CV from a single YAML source.

Recommended layout:
  _data/cv.yml              # canonical CV data
  templates/cv.tex.j2       # LaTeX/Jinja template
  scripts/render_cv.py      # this script
  build/cv.tex              # generated LaTeX
  assets/pdf/cv.tex         # generated LaTeX copied next to the PDF
  assets/pdf/cv.pdf         # generated PDF linked from website

Install:
  pip install pyyaml jinja2

Usage:
  python scripts/render_cv.py
  python scripts/render_cv.py --no-pdf
  python scripts/render_cv.py --input _data/cv.yml --template templates/cv.tex.j2 --pdf assets/pdf/cv.pdf

The script supports a simple normalized YAML shape. It also tries to convert common
al-folio `_data/cv.yml` sections, but if your YAML is heavily customized, adjust
`normalize_cv()`.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined


DEFAULT_INPUT = Path("_data/cv.yml")
DEFAULT_TEMPLATE = Path("templates/cv.tex.j2")
DEFAULT_TEX = Path("build/cv.tex")
DEFAULT_PDF = Path("assets/pdf/cv.pdf")
DEFAULT_ASSET_TEX = DEFAULT_PDF.with_suffix(".tex")
DEFAULT_HIGHLIGHT_NAME = "Kevin Galim"

MONTHS = {
    "01": "Jan",
    "02": "Feb",
    "03": "Mar",
    "04": "Apr",
    "05": "May",
    "06": "Jun",
    "07": "Jul",
    "08": "Aug",
    "09": "Sep",
    "10": "Oct",
    "11": "Nov",
    "12": "Dec",
}

VENUE_ABBREVIATIONS = {
    "International Conference on Learning Representations": "ICLR",
    "International Conference on Machine Learning": "ICML",
    "Annual Meeting of the Association for Computational Linguistics": "ACL",
    "Conference of the European Chapter of the Association for Computational Linguistics": "EACL",
    "European Conference on Computer Vision": "ECCV",
    "IEEE/CVF Conference on Computer Vision and Pattern Recognition": "CVPR",
    "IEEE Access": "IEEE Access",
    "ICLR Workshop on Decoding and Generation with Language Models": "ICLR DeLTa Workshop",
}


LATEX_SPECIAL_CHARS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "–": "--",
    "—": "---",
    "−": "-",
    "‑": "-",
}


def latex_escape(value: Any) -> str:
    """Escape text for LaTeX."""
    if value is None:
        return ""
    text = str(value)
    return "".join(LATEX_SPECIAL_CHARS.get(ch, ch) for ch in text)


def latex_url(value: Any) -> str:
    """Escape URL minimally for use inside \\href{...}{...}."""
    if value is None:
        return ""
    # Do not escape ':' '/' '?' '&' etc. Hyperref can handle most URL chars.
    # Escape only braces and percent signs to avoid TeX parsing issues.
    return str(value).replace("%", r"\%").replace("{", r"\{").replace("}", r"\}")


def tex_paragraph(value: Any) -> str:
    """Escape text but allow a tiny subset of markdown-style emphasis."""
    text = "" if value is None else str(value)
    text = latex_escape(text)

    # Convert escaped markdown bold markers to LaTeX bold:
    # **foo** -> \textbf{foo}
    text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)

    return text


def tex_authors(value: Any, highlight_name: str = DEFAULT_HIGHLIGHT_NAME) -> str:
    """Escape author list and bold the configured user name."""
    text = latex_escape(value)
    name = latex_escape(highlight_name)
    if name:
        text = text.replace(name, rf"\textbf{{{name}}}")
    return text


def tex_dot_list(value: Any) -> str:
    """Escape an inline list while rendering separators as LaTeX centered dots."""
    if isinstance(value, list):
        text = " · ".join(str(x) for x in value)
    else:
        text = "" if value is None else str(value)
    return latex_escape(text).replace(" · ", r" $\cdot$ ")


def contact_tex_lines(contacts: Any) -> list[str]:
    lines = []
    contacts_list = as_list(contacts)
    for index, contact in enumerate(contacts_list):
        if not isinstance(contact, dict):
            line = latex_escape(contact)
        elif contact.get("url"):
            line = rf"\href{{{latex_url(contact.get('url'))}}}{{{latex_escape(contact.get('label'))}}}"
        else:
            line = latex_escape(contact.get("label"))
        if index < len(contacts_list) - 1:
            line += r" $\cdot$"
        lines.append(line)
    return lines


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def split_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value]
    # Support "A · B · C" or "A, B, C" strings.
    text = str(value)
    if "·" in text:
        return [x.strip() for x in text.split("·") if x.strip()]
    return [x.strip() for x in text.split(",") if x.strip()]


def format_cv_date(value: Any) -> str:
    text = "" if value is None else str(value)
    if not text:
        return ""
    if text.lower() == "present":
        return "Present"
    match = re.fullmatch(r"(\d{4})-(\d{2})(?:-\d{2})?", text)
    if match:
        return f"{MONTHS.get(match.group(2), match.group(2))} {match.group(1)}"
    return text


def format_date_range(start: Any, end: Any) -> str:
    start_text = format_cv_date(start)
    end_text = format_cv_date(end)
    if start_text and end_text:
        return f"{start_text} – {end_text}"
    return start_text or end_text


def normalize_degree(study_type: Any, area: Any) -> str:
    degree = str(study_type or "")
    area_text = str(area or "")
    degree = degree.replace("Master's Degree", "Master's degree")
    degree = degree.replace("Bachelor's Degree", "Bachelor's degree")
    area_text = area_text.replace(" — ", ": ").replace("—", ":")
    return ", ".join(x for x in [degree, area_text] if x)


def venue_label(value: Any) -> str:
    text = str(value or "")
    if "WACV" in text and "Oral" in text:
        return "WACV (Oral)"
    for long_name, short_name in VENUE_ABBREVIATIONS.items():
        if long_name in text:
            return short_name
    return text


def author_list(value: Any) -> str:
    authors = []
    for author in as_list(value):
        text = str(author)
        if text == "Hyung Il Koo" and authors and authors[0] == "Seunghyuk Oh":
            text = "Hyung Koo"
        if text == "Laura Leal-Taixé":
            text = "Laura Leal-Taixe"
        authors.append(text.rstrip("."))
    return ", ".join(authors)


def normalize_ongoing_work(value: Any) -> list[dict[str, Any]]:
    entries = []
    for row in as_list(value):
        if not isinstance(row, dict):
            continue
        status = str(row.get("status", ""))
        venue = str(row.get("venue", ""))
        if status.lower() == "submitted manuscript":
            status_text = "Submitted manuscript"
        elif status and venue and venue not in status:
            status_text = f"{status}, {venue}"
        else:
            status_text = status or venue

        entries.append(
            {
                "title": row.get("title", ""),
                "status": status_text,
                "year": row.get("year") or row.get("releaseDate") or row.get("date") or "",
                "summary": row.get("summary") or row.get("description") or "",
            }
        )
    return entries


def normalize_rendercv_summary(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value:
        return [str(value)]
    return []


def normalize_rendercv_skills(value: Any) -> list[dict[str, Any]]:
    skills = []
    for row in as_list(value):
        if not isinstance(row, dict):
            continue
        category = row.get("category") or row.get("name")
        items = row.get("items") or row.get("keywords")
        if not category:
            continue
        skills.append({"category": str(category), "items": split_items(items)})
    return skills


def rendercv_social_url(source: dict[str, Any], network_name: str) -> str:
    for item in as_list(source.get("social_networks")):
        if not isinstance(item, dict):
            continue
        if str(item.get("network", "")).lower() != network_name.lower():
            continue
        if item.get("url"):
            return str(item["url"])
        username = item.get("username")
        if username and network_name.lower() == "linkedin":
            return f"https://www.linkedin.com/in/{username}/"
    return ""


def section_by_title(sections: list[dict[str, Any]], *names: str) -> dict[str, Any] | None:
    wanted = {n.lower() for n in names}
    for sec in sections:
        if str(sec.get("title", "")).lower() in wanted:
            return sec
    return None


def parse_alfolio_general(sec: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not sec:
        return result
    for row in as_list(sec.get("contents")):
        if isinstance(row, dict):
            for k, v in row.items():
                key = str(k).strip().lower()
                result[key] = v
    return result


def parse_alfolio_time_table(sec: dict[str, Any] | None, kind: str) -> list[dict[str, Any]]:
    if not sec:
        return []
    out = []
    for row in as_list(sec.get("contents")):
        if not isinstance(row, dict):
            continue
        title = row.get("title", "")
        institution = row.get("institution", "")
        department = row.get("department", "")
        year = row.get("year", "")
        location = row.get("location", "")
        description = row.get("description", [])
        if isinstance(description, str):
            bullets = [description]
        else:
            bullets = [str(x) for x in as_list(description)]

        if kind == "experience":
            out.append(
                {
                    "role": title,
                    "organization": institution,
                    "dates": year,
                    "location": location,
                    "bullets": bullets,
                    "technologies": split_items(row.get("technologies")),
                }
            )
        else:
            details = row.get("grade") or row.get("details") or ""
            degree_parts = [str(x) for x in [title, department] if x]
            out.append(
                {
                    "institution": institution or title,
                    "degree": ", ".join(degree_parts) if institution else department,
                    "dates": year,
                    "location": location,
                    "details": details,
                }
            )
    return out


def parse_alfolio_list(sec: dict[str, Any] | None) -> list[str]:
    if not sec:
        return []
    out = []
    for row in as_list(sec.get("contents")):
        if isinstance(row, dict):
            for _, v in row.items():
                out.append(str(v))
        else:
            out.append(str(row))
    return out


def normalize_rendercv(data: dict[str, Any]) -> dict[str, Any] | None:
    source = data.get("cv")
    if not isinstance(source, dict) or not isinstance(source.get("sections"), dict):
        return None

    sections = source["sections"]
    experience = []
    for row in as_list(sections.get("Experience")):
        if not isinstance(row, dict):
            continue
        company = str(row.get("company", ""))
        position = str(row.get("position", ""))
        location = str(row.get("location", ""))
        if company == "Dowosoft | Premium Software Development":
            company = "Freelance"
            position = "Web / AR Developer"
            location = "Munich"
        elif company == "ARRI":
            position = "C++/CUDA software engineer"
            location = "Munich"
        elif company == "Funzin":
            position = "AI/Computer vision research and development"

        bullets = [str(x) for x in as_list(row.get("highlights"))]
        if company == "FuriosaAI":
            bullets = [
                bullet.replace("training, evaluating, and deploying", "training and evaluating").replace(
                    "conferences (ICLR, ICML, ACL, CVPR, ECCV, WACV)",
                    "conferences: ICLR, ICML, ACL, CVPR, ECCV, and WACV",
                )
                for bullet in bullets
            ]

        technologies: list[str] = []
        if company == "Funzin":
            technologies = ["PyTorch", "TensorFlow", "C++", "Python", "TensorRT", "OpenVINO", "ARM NEON"]
        elif company == "Freelance":
            technologies = ["Unity3D", "C#", "JavaScript", "Flutter", "AWS", "Google Cloud"]
        elif company == "ARRI":
            technologies = ["C++", "CUDA", "OpenGL", "OpenCL"]

        experience.append(
            {
                "role": position,
                "organization": company,
                "dates": format_date_range(row.get("start_date"), row.get("end_date")),
                "location": location,
                "bullets": bullets,
                "technologies": technologies,
            }
        )

    education = []
    for row in as_list(sections.get("Education")):
        if not isinstance(row, dict):
            continue
        details = f"Grade: {row.get('score')}" if row.get("score") else ""
        education.append(
            {
                "institution": row.get("institution", ""),
                "degree": normalize_degree(row.get("studyType"), row.get("area")).replace(
                    "Research (Semester Abroad), Computer Graphics",
                    "Research, Computer Graphics",
                ),
                "dates": format_date_range(row.get("start_date"), row.get("end_date")),
                "location": "",
                "details": details,
            }
        )

    publications_raw = [row for row in as_list(sections.get("Publications")) if isinstance(row, dict)]
    first_author = []
    other = []
    for row in publications_raw:
        item = {
            "authors": author_list(row.get("authors")),
            "title": row.get("title", ""),
            "venue": venue_label(row.get("publisher")),
            "year": row.get("releaseDate", ""),
        }
        authors = as_list(row.get("authors"))
        if any(str(author).startswith("Kevin Galim*") for author in authors):
            first_author.append(item)
        else:
            other.append(item)

    publications = []
    if first_author:
        publications.append({"heading": "First-author / co-first-author publications", "items": first_author})
    if other:
        publications.append({"heading": "Other publications", "items": other})

    ongoing_work = normalize_ongoing_work(
        sections.get("Ongoing Work") or sections.get("Selected Ongoing Work")
    )

    summary = normalize_rendercv_summary(source.get("summary"))
    skills = normalize_rendercv_skills(sections.get("Skills"))

    language_order = ["English", "German", "Korean"]
    language_map = {
        str(row.get("name")): str(row.get("summary"))
        for row in as_list(sections.get("Languages"))
        if isinstance(row, dict)
    }
    languages = " · ".join(
        f"{name} ({language_map[name].replace(' (TOPIK Level 5)', '')})"
        for name in language_order
        if name in language_map
    )

    email = source.get("email", "")
    website = source.get("website", "")
    scholar = source.get("google_scholar", "")
    linkedin = rendercv_social_url(source, "LinkedIn")
    contacts = []
    if email:
        contacts.append({"label": email})
    if website:
        contacts.append({"label": str(website).removeprefix("https://").removeprefix("http://"), "url": website})
    if scholar:
        contacts.append({"label": "scholar.google.com", "url": scholar})
    if linkedin:
        contacts.append({"label": str(linkedin).removeprefix("https://www.").removeprefix("https://"), "url": linkedin})

    return {
        "name": source.get("name", ""),
        "tagline": source.get("tagline") or source.get("label", ""),
        "contacts": contacts,
        "summary": summary,
        "experience": experience,
        "education": education,
        "ongoing_work": ongoing_work,
        "publications": publications,
        "skills": skills,
        "languages": languages,
    }


def normalize_cv(data: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize either:
      1. a purpose-built CV YAML with keys like name, tagline, experience, etc.
      2. a common al-folio `_data/cv.yml` section list.
    """
    rendercv = normalize_rendercv(data)
    if rendercv:
        return rendercv

    if "name" in data or "experience" in data or "publications" in data:
        cv = {
            "name": data.get("name", ""),
            "tagline": data.get("tagline") or data.get("label", ""),
            "contacts": data.get("contacts", []),
            "summary": as_list(data.get("summary")),
            "experience": data.get("experience", []),
            "education": data.get("education", []),
            "ongoing_work": data.get("ongoing_work", []),
            "publications": data.get("publications", []),
            "skills": data.get("skills", []),
            "languages": data.get("languages", ""),
        }
        return cv

    # al-folio style commonly has top-level `cv` or a list of sections.
    sections = data.get("cv", data)
    if isinstance(sections, dict):
        sections = sections.get("contents", [])
    if not isinstance(sections, list):
        raise ValueError("Could not understand cv.yml structure. Expected normalized keys or al-folio sections.")

    general = parse_alfolio_general(section_by_title(sections, "General Information", "Basics"))
    summary = parse_alfolio_list(section_by_title(sections, "Summary", "Profile"))
    experience = parse_alfolio_time_table(section_by_title(sections, "Experience", "Work"), "experience")
    education = parse_alfolio_time_table(section_by_title(sections, "Education"), "education")

    skills_sec = section_by_title(sections, "Skills")
    skills = []
    if skills_sec:
        for row in as_list(skills_sec.get("contents")):
            if isinstance(row, dict):
                for k, v in row.items():
                    skills.append({"category": str(k), "items": split_items(v)})

    languages = " · ".join(parse_alfolio_list(section_by_title(sections, "Languages")))

    # Publications are often managed separately in al-folio via BibTeX, so this
    # fallback only works if your cv.yml explicitly includes them.
    publications = []
    pubs_sec = section_by_title(sections, "Publications")
    if pubs_sec:
        items = []
        for row in as_list(pubs_sec.get("contents")):
            if isinstance(row, dict):
                items.append(
                    {
                        "authors": row.get("authors", ""),
                        "title": row.get("title", ""),
                        "venue": row.get("venue", ""),
                        "year": row.get("year", ""),
                    }
                )
            else:
                items.append({"authors": "", "title": str(row), "venue": "", "year": ""})
        publications.append({"heading": "Publications", "items": items})

    name = general.get("full name") or general.get("name") or data.get("name") or ""
    email = general.get("email") or data.get("email") or ""
    website = general.get("website") or data.get("website") or ""
    scholar = general.get("google scholar") or data.get("google_scholar") or ""
    linkedin = general.get("linkedin") or data.get("linkedin") or ""
    contacts = []
    if email:
        contacts.append({"label": email})
    if website:
        contacts.append({"label": str(website).removeprefix("https://").removeprefix("http://"), "url": website})
    if scholar:
        contacts.append({"label": "scholar.google.com", "url": scholar})
    if linkedin:
        contacts.append({"label": str(linkedin).removeprefix("https://www.").removeprefix("https://"), "url": linkedin})

    return {
        "name": name,
        "tagline": data.get("tagline") or data.get("label", ""),
        "contacts": contacts,
        "summary": summary,
        "experience": experience,
        "education": education,
        "ongoing_work": data.get("ongoing_work", []),
        "publications": publications,
        "skills": skills,
        "languages": languages,
    }


def render_tex(input_path: Path, template_path: Path, tex_path: Path, highlight_name: str) -> Path:
    data = yaml.safe_load(input_path.read_text(encoding="utf-8")) or {}
    cv = normalize_cv(data)
    cv["contact_lines"] = contact_tex_lines(cv.get("contacts", []))

    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["tex"] = latex_escape
    env.filters["tex_url"] = latex_url
    env.filters["tex_paragraph"] = tex_paragraph
    env.filters["tex_authors"] = lambda value: tex_authors(value, highlight_name=highlight_name)
    env.filters["tex_dot_list"] = tex_dot_list

    template = env.get_template(template_path.name)
    rendered = template.render(cv=cv)

    tex_path.parent.mkdir(parents=True, exist_ok=True)
    tex_path.write_text(rendered, encoding="utf-8")
    return tex_path


def copy_tex_to_asset(tex_path: Path, asset_tex_path: Path) -> None:
    """Copy the generated TeX beside the published PDF."""
    if tex_path.resolve() == asset_tex_path.resolve():
        return

    asset_tex_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tex_path, asset_tex_path)


def compile_pdf(tex_path: Path, pdf_path: Path, engine: str = "pdflatex") -> None:
    if shutil.which(engine) is None:
        raise RuntimeError(f"{engine} not found. Generated {tex_path}, but could not compile PDF.")

    workdir = tex_path.parent
    cmd = [
        engine,
        "-interaction=nonstopmode",
        "-halt-on-error",
        tex_path.name,
    ]

    # Run twice for stable links/references, though this CV has no citations.
    for _ in range(2):
        subprocess.run(cmd, cwd=workdir, check=True)

    built_pdf = tex_path.with_suffix(".pdf")
    if not built_pdf.exists():
        raise RuntimeError(f"Expected PDF was not produced: {built_pdf}")

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built_pdf, pdf_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render CV from YAML to LaTeX/PDF.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--tex", type=Path, default=DEFAULT_TEX)
    parser.add_argument("--asset-tex", type=Path, default=DEFAULT_ASSET_TEX)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--engine", default="pdflatex", help="LaTeX engine: pdflatex, xelatex, lualatex")
    parser.add_argument("--highlight-name", default=DEFAULT_HIGHLIGHT_NAME)
    parser.add_argument("--no-pdf", action="store_true", help="Only generate .tex, do not compile PDF.")
    args = parser.parse_args()

    tex_path = render_tex(args.input, args.template, args.tex, args.highlight_name)
    print(f"Wrote LaTeX: {tex_path}")
    copy_tex_to_asset(tex_path, args.asset_tex)
    print(f"Wrote LaTeX copy: {args.asset_tex}")

    if args.no_pdf:
        return

    try:
        compile_pdf(tex_path, args.pdf, args.engine)
        print(f"Wrote PDF: {args.pdf}")
    except Exception as exc:
        print(f"PDF compilation skipped/failed: {exc}")
        print("You can compile manually, for example:")
        print(f"  cd {tex_path.parent} && {args.engine} -interaction=nonstopmode -halt-on-error {tex_path.name}")


if __name__ == "__main__":
    main()
