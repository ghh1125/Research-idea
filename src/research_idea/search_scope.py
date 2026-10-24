"""Provider-independent literature boundaries, checked again after retrieval."""
from __future__ import annotations

from datetime import date
import calendar
import fnmatch
import re

from .venues import DEFAULT_AI_VENUES

AI_VENUES = list(DEFAULT_AI_VENUES)


def recent_defaults() -> dict:
    today = date.today()
    return {"search_since": months_before(today, 12).isoformat(), "search_until": today.isoformat(),
            "search_cs_only": True, "arxiv_categories": ["cs.*"]}


def months_before(day, months):
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def normalize_scope(since="", until="", cs_only=False, arxiv_categories=None,
                    conference_policy="window") -> dict:
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
    if not isinstance(conference_policy, str) or conference_policy not in {"latest", "window"}:
        raise ValueError("conference_policy must be latest or window")
    return {**values, "cs_only": cs_only, "arxiv_categories": list(dict.fromkeys(categories)),
            "conference_policy": conference_policy}


def config_scope(config: dict, purpose='strategy') -> dict:
    since, until = config.get('search_since', ''), config.get('search_until', '')
    if config.get('search_date_mode') == 'rolling':
        end = date.today()
        until = end.isoformat()
        months = config.get('novelty_months', 6) if purpose == 'novelty' else config.get('strategy_months', 12)
        since = months_before(end, months).isoformat()
    elif purpose == 'novelty':
        end = date.fromisoformat(until) if until else date.today()
        since = max(since, months_before(end, config.get('novelty_months', 6)).isoformat())
    return normalize_scope(since, until,
                           config.get("search_cs_only", False), config.get("arxiv_categories", []),
                           config.get("conference_policy", "latest"))


def exclusion_reason(paper: dict, scope: dict, source: str, *, verified_venue=False) -> str | None:
    """Missing metadata cannot establish that a hard filter was satisfied."""
    if verified_venue and source != 'arxiv' and scope.get('conference_policy') == 'latest':
        # Edition selection happens independently of the topical query. Its
        # papers may predate the rolling preprint window (or first appear on
        # arXiv years before their conference publication).
        scope = dict(scope, since='')
    published = paper.get("publication_date")
    if scope["since"] or scope["until"]:
        try:
            parsed = date.fromisoformat(published) if isinstance(published, str) else None
        except ValueError:
            parsed = None
        if parsed is None:
            edition = paper.get('conference_year')
            edition_date = verified_venue and scope.get('conference_policy') == 'latest' and type(edition) is int
            period = paper.get('publication_period') or (str(edition) if edition_date else '')
            if (not edition_date and paper.get('source') != 'official_proceedings') or not re.fullmatch(r'\d{4}(?:-\d{2})?', period):
                return "missing or invalid publication date"
            try:
                year, month = int(period[:4]), int(period[5:]) if len(period) == 7 else 1
                lower = date(year, month, 1).isoformat()
                upper_month = month if len(period) == 7 else 12
                upper = date(year, upper_month, calendar.monthrange(year, upper_month)[1]).isoformat()
            except ValueError:
                return "missing or invalid publication date"
            if (scope['since'] and upper < scope['since']) or (scope['until'] and lower > scope['until']):
                return "publication period outside requested window"
            paper['date_window_match'] = 'period_overlap'
            published = None
        if published and scope["since"] and published < scope["since"]:
            return "publication date before requested window"
        if published and scope["until"] and published > scope["until"]:
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
