"""Provider-independent literature boundaries, checked again after retrieval."""
from __future__ import annotations

from datetime import date
import fnmatch
import re

AI_VENUES = ["NeurIPS", "ICML", "ICLR", "ACL", "EMNLP", "NAACL", "COLM", "AAAI", "IJCAI"]


def recent_defaults() -> dict:
    today = date.today()
    return {"search_since": f"{today.year - 1}-01-01", "search_until": today.isoformat(),
            "search_cs_only": True, "arxiv_categories": ["cs.*"]}


def normalize_scope(since="", until="", cs_only=False, arxiv_categories=None) -> dict:
    values = {"since": since, "until": until}
    for key, value in values.items():
        if not isinstance(value, str):
            raise ValueError(f"search_{key} must be an ISO date or an empty string")
        if value:
            try:
                parsed = date.fromisoformat(value)
            except ValueError:
                raise ValueError(f"search_{key} must use YYYY-MM-DD") from None
            if parsed.isoformat() != value:
                raise ValueError(f"search_{key} must use YYYY-MM-DD")
    if since and until and since > until:
        raise ValueError("search_since must not be later than search_until")
    if type(cs_only) is not bool:
        raise ValueError("search_cs_only must be a boolean")
    if arxiv_categories is not None and not isinstance(arxiv_categories, list):
        raise ValueError("arxiv_categories must be a list of arXiv category codes")
    categories = ["cs.*"] if arxiv_categories is None and cs_only else (arxiv_categories or [])
    if not isinstance(categories, list) or any(
        not isinstance(item, str) or not re.fullmatch(r"[a-z][a-z-]*(?:\.(?:[A-Za-z]{2}|\*))?", item)
        for item in categories
    ):
        raise ValueError("arxiv_categories must be a list of arXiv category codes, such as cs.* or cs.CL")
    return {**values, "cs_only": cs_only, "arxiv_categories": list(dict.fromkeys(categories))}


def config_scope(config: dict) -> dict:
    return normalize_scope(config.get("search_since", ""), config.get("search_until", ""),
                           config.get("search_cs_only", False), config.get("arxiv_categories", []))


def exclusion_reason(paper: dict, scope: dict, source: str, *, verified_venue=False) -> str | None:
    """Missing metadata cannot establish that a hard filter was satisfied."""
    published = paper.get("publication_date")
    if scope["since"] or scope["until"]:
        try:
            parsed = date.fromisoformat(published) if isinstance(published, str) else None
        except ValueError:
            parsed = None
        if parsed is None:
            return "missing or invalid publication date"
        if scope["since"] and published < scope["since"]:
            return "publication date before requested window"
        if scope["until"] and published > scope["until"]:
            return "publication date after requested window"
    if source == "arxiv":
        categories = paper.get("categories", [])
        if scope["cs_only"] and not any(c.startswith("cs.") for c in categories):
            return "no verified CS category"
        requested = scope["arxiv_categories"]
        if requested and not any(fnmatch.fnmatchcase(c, pattern) for c in categories for pattern in requested):
            return "outside requested arXiv categories"
    elif scope["cs_only"] and not verified_venue and "17" not in paper.get("field_ids", []):
        return "no verified Computer Science field"
    return None
