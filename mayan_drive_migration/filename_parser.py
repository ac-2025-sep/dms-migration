from __future__ import annotations

import re
from pathlib import Path


FILENAME_PATTERN = re.compile(
    r"^(?P<content_code>[A-Za-z0-9]+)_"
    r"(?P<channel_or_format>[A-Za-z0-9]+)_"
    r"(?P<language>[A-Za-z0-9-]+)_"
    r"(?P<section_code>[A-Za-z0-9]+)_"
    r"(?P<version>v\d+(?:\.\d+)?)"
    r"\s*-\s*"
    r"(?P<rest>.+)$",
    re.IGNORECASE,
)


def parse_filename(filename: str) -> dict[str, str]:
    """Parse business metadata from a file name, falling back without failing."""
    original = Path(filename).name
    stem = Path(original).stem.strip()
    match = FILENAME_PATTERN.match(stem)
    if not match:
        return {
            "original_filename": original,
            "title": _clean_text(stem),
        }

    values = {key: _clean_text(value) for key, value in match.groupdict().items() if key != "rest"}
    stage, title = _split_stage_title(match.group("rest"))
    values.update(
        {
            "document_stage": stage,
            "title": title,
            "original_filename": original,
        }
    )
    return values


def _split_stage_title(rest: str) -> tuple[str, str]:
    parts = [_clean_text(part) for part in re.split(r"\s+-\s+", rest, maxsplit=1)]
    if len(parts) == 2:
        return parts[0], parts[1]

    text = _clean_text(rest)
    base_doc_match = re.search(r"\bbase\s*doc(?:ument)?\b", text, flags=re.IGNORECASE)
    if base_doc_match:
        stage = _clean_text(base_doc_match.group(0))
        title = _clean_text((text[: base_doc_match.start()] + " " + text[base_doc_match.end() :]).strip(" -"))
        return _normalize_stage(stage), title or text

    draft_match = re.search(r"\bdraft(?:-\d+)?\b", text, flags=re.IGNORECASE)
    if draft_match:
        stage = _clean_text(draft_match.group(0))
        title = _clean_text((text[: draft_match.start()] + " " + text[draft_match.end() :]).strip(" -"))
        return stage, title or text

    return "", text


def _normalize_stage(value: str) -> str:
    if value.lower().replace(" ", "") in {"basedoc", "basedocument"}:
        return "Base Doc"
    return value


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("_", " ")).strip(" -")
