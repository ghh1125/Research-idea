"""A small explicit venue registry, not a complete/current ranking catalog.

The versioned preset follows the AI conference section of CCF's 2022 catalog.
Other entries have no CCF grade implied. Matching uses publication-source
metadata only; paper titles are never used to infer a venue.
"""
from __future__ import annotations

import re

CCF_CATALOG_URL = "https://www.ccf.org.cn/Academic_Evaluation/AI/"
CCF_2022_AI = ("AAAI", "NeurIPS", "ACL", "CVPR", "ICCV", "ICML", "IJCAI")
VENUES = {
    "AAAI": ("AAAI Conference on Artificial Intelligence", "Proceedings of the AAAI Conference on Artificial Intelligence"),
    "NeurIPS": ("Conference on Neural Information Processing Systems", "Advances in Neural Information Processing Systems", "Neural Information Processing Systems", "NIPS"),
    "ACL": ("Annual Meeting of the Association for Computational Linguistics",),
    "CVPR": ("IEEE/CVF Conference on Computer Vision and Pattern Recognition", "IEEE/CVF Computer Vision and Pattern Recognition Conference", "IEEE Conference on Computer Vision and Pattern Recognition", "Conference on Computer Vision and Pattern Recognition"),
    "ICCV": ("International Conference on Computer Vision", "IEEE/CVF International Conference on Computer Vision", "IEEE International Conference on Computer Vision"),
    "ICML": ("International Conference on Machine Learning",),
    "IJCAI": ("International Joint Conference on Artificial Intelligence",),
    "EMNLP": ("Conference on Empirical Methods in Natural Language Processing", "Empirical Methods in Natural Language Processing"),
    "NAACL": ("Conference of the North American Chapter of the Association for Computational Linguistics: Human Language Technologies", "Conference of the Nations of the Americas Chapter of the Association for Computational Linguistics: Human Language Technologies", "North American Chapter of the Association for Computational Linguistics", "Nations of the Americas Chapter of the Association for Computational Linguistics", "NAACL-HLT"),
    "COLM": ("Conference on Language Modeling",),
    "ICLR": ("International Conference on Learning Representations",),
}
PRESETS = {"ccf-a-ai-2022": CCF_2022_AI}
# Source lookup must accommodate renamed series as well as name matching.
# These are metadata searches; the returned names still require exact matching.
SOURCE_QUERIES = {
    "NeurIPS": ("Neural Information Processing Systems",),
    "NAACL": (VENUES["NAACL"][1], VENUES["NAACL"][0]),
}


def _key(value: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


def normalize_venues(venues: list[str] | None) -> list[str]:
    """Validate exact aliases and expand the explicitly dated preset."""
    if venues is None:
        return []
    if not isinstance(venues, list) or any(not isinstance(v, str) for v in venues):
        raise ValueError("Venues must be a list of conference names")
    aliases = {_key(alias): name for name, names in VENUES.items() for alias in (name, *names)}
    result = []
    for value in venues:
        # Both --venues ACL EMNLP and --venues ACL,EMNLP are convenient.
        for item in value.split(","):
            item = item.strip()
            if not item:
                raise ValueError("Venue names must not be empty")
            if item.casefold() in PRESETS:
                names = PRESETS[item.casefold()]
            elif _key(item) in aliases:
                names = (aliases[_key(item)],)
            else:
                raise ValueError(f"Unsupported venue {item!r}; use 'research-idea venues' to list supported names")
            for name in names:
                if name not in result:
                    result.append(name)
    return result


def supported_venues() -> list[dict]:
    return [{"code": name, "name": name, "description": aliases[0],
             "ccf_2022_ai_grade": "A" if name in CCF_2022_AI else None}
            for name, aliases in VENUES.items()] + [
        {"code": "ccf-a-ai-2022", "name": "ccf-a-ai-2022",
         "description": "CCF 2022 AI conference A-list only; not all CCF-A venues or a current ranking",
         "expands_to": list(CCF_2022_AI), "catalog_url": CCF_CATALOG_URL}]


def canonical_venue(source_name: str) -> str | None:
    """Recognize exact series names or dated main-proceedings names.

    Annual ordinals/year and main long/short-paper volume decorations may vary.
    Findings, workshops, demos and student proceedings are separate venues and
    deliberately never promoted to the main conference.
    """
    if not isinstance(source_name, str):
        return None
    text = source_name.casefold()
    if re.search(r"\b(findings|workshops?|demonstrations?|demos?|tutorials?|student|industry|companion|adjunct)\b", text):
        return None
    text = re.sub(r"\(volume\s+\d+\s*:\s*(?:long|short)\s+papers\)", "", text)
    text = re.sub(r"\((?:long|short)\s+papers\)", "", text)
    text = re.sub(r"\b(?:19|20)\d{2}\b|\b\d+(?:st|nd|rd|th)\b", " ", text)
    text = re.sub(r"\b(?:first|second|third|fourth|fifth|annual)\b", " ", text)
    text = re.sub(r"^\s*proceedings\s+of\s+(?:the\s+)?", "", text)
    key = _key(text)
    for name, aliases in VENUES.items():
        for alias in (name, *aliases):
            normalized = re.sub(r"\bannual\b", " ", alias.casefold())
            normalized = re.sub(r"^proceedings\s+of\s+(?:the\s+)?", "", normalized)
            if key == _key(normalized):
                return name
    return None
