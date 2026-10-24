"""A small explicit venue registry, not a complete/current ranking catalog.

Versioned ranking presets and the user's research scope are separate.
Entries outside a dated ranking subset have no grade implied. Matching uses publication-source
metadata only; paper titles are never used to infer a venue.
"""
from __future__ import annotations

import re

CCF_CATALOG_URL = "https://www.ccf.org.cn/Academic_Evaluation/AI/"
CCF_2026_AI = ("AAAI", "NeurIPS", "ACL", "CVPR", "ICCV", "ICML", "ICLR")
CCF_2026_B = ("EMNLP", "NAACL", "IJCAI", "AAMAS")
CCF_2026_COPY_URL = "https://dengpingfan.github.io/papers/CCF-Recommend-2026.pdf"
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
    "KDD": ("ACM SIGKDD International Conference on Knowledge Discovery and Data Mining", "ACM SIGKDD Conference on Knowledge Discovery and Data Mining", "ACM International Conference on Knowledge Discovery and Data Mining"),
    "ICDM": ("IEEE International Conference on Data Mining", "International Conference on Data Mining"),
    "ICDE": ("IEEE International Conference on Data Engineering", "International Conference on Data Engineering"),
    "SIGMOD": ("ACM SIGMOD International Conference on Management of Data", "International Conference on Management of Data", "ACM Special Interest Group on Management of Data Conference"),
    "VLDB": ("Proceedings of the VLDB Endowment", "PVLDB", "International Conference on Very Large Data Bases", "International Conference on Very Large Databases"),
    "ACMMM": ("ACM International Conference on Multimedia", "ACM Multimedia", "ACM MM", "MM"),
    "SIGIR": ("International ACM SIGIR Conference on Research and Development in Information Retrieval", "ACM SIGIR Conference on Research and Development in Information Retrieval", "ACM International Conference on Research and Development in Information Retrieval"),
    "WWW": ("ACM Web Conference", "The Web Conference", "International World Wide Web Conference", "International Conference on World Wide Web"),
}
# PACMMOD also publishes PODS: retain its actual series name in results rather
# than labelling every article as a verified SIGMOD conference paper.
PUBLICATION_SERIES = {"PACMMOD": ("Proceedings of the ACM on Management of Data",)}
RELATED_SOURCE_VENUES = {"SIGMOD": ("PACMMOD",)}
# Verified 2026-10-23 from the official ICORE2026 portal (rank-sorted pages 1–2).
CORE_2026_URL = "https://portal.core.edu.au/conf-ranks/?search=&by=all&source=ICORE2026&sort=arank&page=1"
CORE_2026_RECORDS = [
    {'code': 'AAAI', 'title': 'National Conference of the American Association for Artificial Intelligence', 'field': '4602'},
    {'code': 'ACL', 'title': 'Association for Computational Linguistics', 'field': '4602'},
    {'code': 'ACMMM', 'title': 'ACM Multimedia', 'field': '4603'},
    {'code': 'ASE', 'title': 'Automated Software Engineering Conference', 'field': '4612'},
    {'code': 'ASPLOS', 'title': 'Architectural Support for Programming Languages and Operating Systems', 'field': '4612'},
    {'code': 'CAV', 'title': 'Computer Aided Verification', 'field': '4612'},
    {'code': 'CCS', 'title': 'ACM Conference on Computer and Communications Security', 'field': '4604'},
    {'code': 'CHI', 'title': 'International Conference on Human Factors in Computing Systems', 'field': '4608'},
    {'code': 'COLT', 'title': 'Conference on Learning Theory', 'field': '4611'},
    {'code': 'CRYPTO', 'title': 'Advances in Cryptology', 'field': '4604'},
    {'code': 'CVPR', 'title': 'IEEE Conference on Computer Vision and Pattern Recognition', 'field': '4603'},
    {'code': 'DAC', 'title': 'Design Automation Conf', 'field': 'CSE'},
    {'code': 'EC', 'title': 'ACM Conference on Economics and Computation', 'field': '4602'},
    {'code': 'ECCV', 'title': 'European Conference on Computer Vision', 'field': '4603'},
    {'code': 'EMNLP', 'title': 'Empirical Methods in Natural Language Processing', 'field': '4602'},
    {'code': 'EuroCrypt', 'title': 'International Conference on the Theory and Application of Cryptographic Techniques', 'field': '4604'},
    {'code': 'FOCS', 'title': 'IEEE Symposium on Foundations of Computer Science', 'field': '4613'},
    {'code': 'FSE', 'title': 'ACM International Conference on the Foundations of Software Engineering (was ESEC/FSE, changed 2024; duplicate previously listed as ESEC, removed from DB)', 'field': '4612'},
    {'code': 'HPCA', 'title': 'International Symposium on High Performance Computer Architecture', 'field': 'CSE'},
    {'code': 'HRI', 'title': 'ACM/IEEE International Conference on Human-Robot Interaction', 'field': '4608'},
    {'code': 'ICALP', 'title': 'International Colloquium on Automata Languages and Programming', 'field': '4613'},
    {'code': 'ICAPS', 'title': 'International Conference on Automated Planning and Scheduling', 'field': '4602'},
    {'code': 'ICCV', 'title': 'IEEE International Conference on Computer Vision', 'field': '4603'},
    {'code': 'ICDE', 'title': 'International Conference on Data Engineering', 'field': '4605'},
    {'code': 'ICDM', 'title': 'IEEE International Conference on Data Mining', 'field': '4605'},
    {'code': 'ICLR', 'title': 'International Conference on Learning Representations', 'field': '4611'},
    {'code': 'ICML', 'title': 'International Conference on Machine Learning', 'field': '4611'},
    {'code': 'ICRA', 'title': 'IEEE International Conference on Robotics and Automation', 'field': '4602'},
    {'code': 'ICSE', 'title': 'International Conference on Software Engineering', 'field': '4612'},
    {'code': 'IJCAI', 'title': 'International Joint Conference on Artificial Intelligence', 'field': '4602'},
    {'code': 'INFOCOM', 'title': 'IEEE International Conference on Computer Communications', 'field': '4606'},
    {'code': 'ISCA', 'title': 'ACM International Symposium on Computer Architecture', 'field': 'CSE'},
    {'code': 'ISMAR', 'title': 'IEEE/ACM International Symposium on Mixed and Augmented Reality', 'field': '4607'},
    {'code': 'KDD', 'title': 'ACM International Conference on Knowledge Discovery and Data Mining', 'field': '4605'},
    {'code': 'KR', 'title': 'International Conference on the Principles of Knowledge Representation and Reasoning', 'field': '4602'},
    {'code': 'LICS', 'title': 'IEEE Symposium on Logic in Computer Science', 'field': '4613'},
    {'code': 'MICRO', 'title': 'International Symposium on Microarchitecture', 'field': 'CSE'},
    {'code': 'MOBICOM', 'title': 'ACM International Conference on Mobile Computing and Networking', 'field': '4606'},
    {'code': 'NDSS', 'title': 'Usenix Network and Distributed System Security Symposium', 'field': '4604'},
    {'code': 'NeurIPS', 'title': 'Advances in Neural Information Processing Systems (was NIPS)', 'field': '4611'},
    {'code': 'OSDI', 'title': 'Usenix Symposium on Operating Systems Design and Implementation', 'field': '4606'},
    {'code': 'PERCOM', 'title': 'IEEE International Conference on Pervasive Computing and Communications', 'field': '4608'},
    {'code': 'PLDI', 'title': 'ACM-SIGPLAN Conference on Programming Language Design and Implementation', 'field': '4612'},
    {'code': 'PODC', 'title': 'ACM Symposium on Principles of Distributed Computing', 'field': '4606'},
    {'code': 'PODS', 'title': 'ACM SIGMOD-SIGACT-SIGART Conference on Principles of Database Systems', 'field': '4605'},
    {'code': 'POPL', 'title': 'ACM-SIGACT Symposium on Principles of Programming Languages', 'field': '4612'},
    {'code': 'SIGCOMM', 'title': 'ACM Conference on Applications, Technologies, Architectures, and Protocols for Computer Communication', 'field': '4606'},
    {'code': 'SIGGRAPH', 'title': 'ACM SIG International Conference on Computer Graphics and Interactive Techniques', 'field': '4607'},
    {'code': 'SiggraphA', 'title': 'SIGGRAPH Asia', 'field': '4607'},
    {'code': 'SIGIR', 'title': 'ACM International Conference on Research and Development in Information Retrieval', 'field': '4605'},
    {'code': 'SIGMETRICS', 'title': 'Measurement and Modeling of Computer Systems', 'field': '4612'},
    {'code': 'SIGMOD', 'title': 'ACM Special Interest Group on Management of Data Conference', 'field': '4605'},
    {'code': 'SoCG', 'title': 'International Symposium on Computational Geometry', 'field': '4613'},
    {'code': 'SODA', 'title': 'ACM/SIAM Symposium on Discrete Algorithms', 'field': '4613'},
    {'code': 'SOSP', 'title': 'ACM SIGOPS Symposium on Operating Systems Principles', 'field': '4606'},
    {'code': 'SP', 'title': 'IEEE Symposium on Security and Privacy', 'field': '4604'},
    {'code': 'STOC', 'title': 'ACM Symposium on Theory of Computing', 'field': '4613'},
    {'code': 'UIST', 'title': 'ACM Symposium on User Interface Software and Technology', 'field': '4608'},
    {'code': 'USENIX-Security', 'title': 'Usenix Security Symposium', 'field': '4604'},
    {'code': 'VLDB', 'title': 'International Conference on Very Large Databases', 'field': '4605'},
    {'code': 'VR', 'title': 'IEEE Conference on Virtual Reality and 3D User Interfaces', 'field': '4607'},
    {'code': 'WWW', 'title': 'International World Wide Web Conference', 'field': '4606'},
]
CORE_2026_ASTAR = tuple(row['code'] for row in CORE_2026_RECORDS)
CORE_2026_AI = tuple(row['code'] for row in CORE_2026_RECORDS if row['field'] in {'4602', '4603', '4611'})
TH_CPL_URL = "https://numbda.cs.tsinghua.edu.cn/~yuwj/TH-CPL.pdf"
TH_CPL_2019_AI = ('CVPR', 'ICCV', 'ICML', 'ACL', 'ECCV', 'COLT', 'NeurIPS', 'AAAI', 'EMNLP', 'ICRA', 'ICLR', 'RSS')
for _row in CORE_2026_RECORDS:
    if _row['code'] not in VENUES:
        VENUES[_row['code']] = (re.sub(r' \(was .*\)$', '', _row['title']),)
VENUES['RSS'] = ('Robotics: Science and Systems', 'Robotics Science and Systems')
VENUES['AAMAS'] = ('International Joint Conference on Autonomous Agents and Multiagent Systems', 'International Joint Conference on Autonomous Agents and Multi-agent Systems')
# User-facing LLM/NLP/Agent default; ranking catalogs are metadata, not automatic scope expansion.
DEFAULT_AI_VENUES = ('NeurIPS', 'ICML', 'ICLR', 'ACL', 'EMNLP', 'NAACL', 'COLM', 'AAAI', 'IJCAI', 'AAMAS',
                     'KDD', 'ICDM', 'ICDE', 'SIGMOD', 'VLDB', 'ACMMM', 'CVPR', 'ICCV', 'SIGIR', 'WWW')
PRESETS = {"ai-recommended": DEFAULT_AI_VENUES, "tsinghua-a-ai-2019": TH_CPL_2019_AI, "core-astar-ai-2026": CORE_2026_AI, "core-astar-2026": CORE_2026_ASTAR, "ccf-a-ai": CCF_2026_AI, "ccf-a-ai-2026": CCF_2026_AI, "ccf-a-ai-2022": CCF_2022_AI}
# Source lookup must accommodate renamed series as well as name matching.
# These are metadata searches; the returned names still require exact matching.
SOURCE_QUERIES = {
    "NeurIPS": ("Neural Information Processing Systems",),
    "NAACL": (VENUES["NAACL"][1], VENUES["NAACL"][0]),
    "KDD": ("Knowledge Discovery and Data Mining",),
    "ICDM": ("International Conference on Data Mining",),
    "ICDE": ("International Conference on Data Engineering",),
    "SIGMOD": ("Proceedings of the ACM on Management of Data", "International Conference on Management of Data"),
    "VLDB": ("Proceedings of the VLDB Endowment", "Very Large Data Bases"),
    "ACMMM": ("ACM International Conference on Multimedia",),
    "SIGIR": ("Research and Development in Information Retrieval",),
    "WWW": ("Web Conference", "World Wide Web"),
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
             "ccf_2026_ai_grade": "A" if name in CCF_2026_AI else "B" if name in CCF_2026_B else None,
             "ccf_catalog_year": 2026, "core_2026_grade": "A*" if name in CORE_2026_ASTAR else None,
             "tsinghua_2019_ai_grade": "A" if name in TH_CPL_2019_AI else None, "ccf_2022_ai_grade": "A" if name in CCF_2022_AI else None}
            for name, aliases in VENUES.items()] + [
        {"code": "ai-recommended", "name": "ai-recommended", "description": "Selected LLM/NLP/Agent, data mining, data management, retrieval, Web, vision and multimedia venues; papers are screened for topic relevance", "expands_to": list(DEFAULT_AI_VENUES)},
        {"code": "tsinghua-a-ai-2019", "name": "tsinghua-a-ai-2019", "description": "TH-CPL 2019 AI/Pattern Recognition A conferences; verified public university document, not asserted to be a 2026 revision", "expands_to": list(TH_CPL_2019_AI), "catalog_url": TH_CPL_URL},
        {"code": "core-astar-ai-2026", "name": "core-astar-ai-2026", "description": "ICORE2026 A* in FoR 4602, 4603 and 4611", "expands_to": list(CORE_2026_AI), "catalog_url": CORE_2026_URL},
        {"code": "core-astar-2026", "name": "core-astar-2026", "description": "All 62 ICORE2026 A* conferences, across CS fields", "expands_to": list(CORE_2026_ASTAR), "catalog_url": CORE_2026_URL},
        {"code": "ccf-a-ai-2026", "name": "ccf-a-ai-2026",
         "description": "CCF 2026 (7th edition) AI A-list; full/regular papers only, no short/findings/workshop grading implied",
         "expands_to": list(CCF_2026_AI), "catalog_url": CCF_CATALOG_URL,
         "verified_document": CCF_2026_COPY_URL, "document_pages": [57, 58]},
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
    for name, aliases in {**VENUES, **PUBLICATION_SERIES}.items():
        for alias in (name, *aliases):
            normalized = re.sub(r"\bannual\b", " ", alias.casefold())
            normalized = re.sub(r"^proceedings\s+of\s+(?:the\s+)?", "", normalized)
            if key == _key(normalized):
                return name
    return None
