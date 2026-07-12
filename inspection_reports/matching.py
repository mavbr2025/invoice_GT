from __future__ import annotations

import re
from pathlib import PurePosixPath

from inspection_reports.models import SharePointItem


def normalize_match_value(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def build_match_terms(values: tuple[str, ...]) -> tuple[str, ...]:
    terms: list[str] = []
    for value in values:
        normalized = normalize_match_value(value)
        # Avoid weak matches such as two-letter country codes or generic words.
        if len(normalized) >= 4:
            terms.append(normalized)

    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            unique.append(term)
    return tuple(unique)


def item_matches_terms(item: SharePointItem, terms: tuple[str, ...]) -> bool:
    if not terms:
        return False
    haystack = normalize_match_value(f"{item.path} {item.name}")
    return any(term in haystack for term in terms)


def caption_from_item_path(path: str) -> str:
    name = PurePosixPath(path).name
    stem = PurePosixPath(name).stem
    return " ".join(part for part in re.split(r"[_\\-]+", stem) if part).strip() or stem
