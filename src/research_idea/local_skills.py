"""Discover optional local skills and snapshot only explicitly selected text.

Discovery does not activate skills. Loading returns inert Markdown; it does not
follow reference links, download resources, invoke helpers, or run scripts.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

MAX_FILE_BYTES = 32 * 1024
MAX_DISCOVERY_ENTRIES = 5000
MAX_DEPTH = 3
ALL_STAGES = ("plan_search", "extract", "read_section", "paper_card", "audit_claims", "map", "propose", "develop", "review", "refine", "inspect_source")
BUILTIN_ROOT = Path(__file__).parent / "builtin_skills"
BUILTIN_NAMES = (
    "research-idea-read-evidence", "research-idea-motivation", "research-idea-compare-methods",
    "research-idea-build-mechanism", "research-idea-check-feasibility", "research-idea-design-falsification",
    "research-idea-audit-claims", "research-idea-analyze-paper",
)

STAGE_MAP = {
    "research-idea-read-evidence": ("plan_search", "extract", "read_section", "inspect_source"),
    "research-idea-analyze-paper": ("read_section", "paper_card"),
    "research-idea-motivation": ("map", "propose", "develop", "refine", "review"),
    "research-idea-compare-methods": ("inspect_source", "develop", "refine", "review"),
    "research-idea-build-mechanism": ("propose", "develop", "refine"),
    "research-idea-check-feasibility": ("develop", "refine", "review"),
    "research-idea-design-falsification": ("develop", "refine", "review"),
    "research-idea-audit-claims": ("audit_claims", "extract", "inspect_source", "develop", "refine", "review"),
    "ccf-idea-optimizer": ("map", "propose", "develop", "refine"),
    "ccf-idea-reviewer": ("review",),
    "ccf-experiment-designer": ("develop", "refine", "review"),
    "ccf-literature-searcher": ("map", "inspect_source"),
    "nature-paper-card": ("extract", "read_section", "paper_card", "inspect_source"),
    "nature-reader": ("extract", "inspect_source"),
    "nature-academic-search": ("map", "inspect_source"),
    "idea-creator": ("map", "propose"),
    "idea-discovery": ("map", "propose", "develop", "refine"),
    "research-refine": ("develop", "refine"),
    "research-review": ("review",),
    "experiment-plan": ("develop", "refine", "review"),
    "experiment-bridge": ("develop", "refine", "review"),
    "novelty-check": ("review", "inspect_source"),
    "research-lit": ("extract", "map", "inspect_source"),
}


class LocalSkillError(ValueError):
    """An explicit skill selection cannot be resolved faithfully."""


def _scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, str) else value
        except ValueError:
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def _metadata(text: str, fallback: str) -> tuple[str, str]:
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        return fallback, ""
    values: dict[str, str] = {}
    current: str | None = None
    for line in lines[1:]:
        if line.strip() in {"---", "..."}:
            break
        match = re.match(r"^(name|description):\s*(.*)$", line)
        if match:
            current = match[1]
            value = match[2].strip()
            values[current] = "" if value in {"|", "|-", "|+", ">", ">-", ">+"} else _scalar(value)
        elif current and line[:1].isspace():
            values[current] = (values.get(current, "") + " " + line.strip()).strip()
        elif line.strip():
            current = None
    return values.get("name", "").strip() or fallback, values.get("description", "").strip()


def _roots(project: Path | None, extra_roots: list[str] | None) -> list[Path]:
    project = (Path(project) if project is not None else Path.cwd()).expanduser().resolve()
    home = Path.home()
    codex = Path(os.environ.get("CODEX_HOME") or home / ".codex").expanduser()
    roots = [BUILTIN_ROOT, project / ".agents/skills", project / ".codex/skills", project / ".claude/skills",
             home / ".agents/skills", codex / "skills", home / ".claude/skills"]
    for raw in extra_roots or []:
        if not isinstance(raw, str) or not raw.strip():
            raise LocalSkillError("Skill roots must be nonempty directory paths")
        path = Path(raw).expanduser()
        roots.append(path if path.is_absolute() else project / path)
    return list(dict.fromkeys(path.resolve() for path in roots))


def discovery_roots(project: Path | None = None, extra_roots: list[str] | None = None) -> list[str]:
    """Return resolved candidate roots for diagnostics, including absent roots."""
    return [str(path) for path in _roots(project, extra_roots)]


def builtin_skill_paths() -> list[str]:
    """Return shipped built-in skill files that exist; do not activate them."""
    return [str((BUILTIN_ROOT / name / "SKILL.md").resolve()) for name in BUILTIN_NAMES
            if (BUILTIN_ROOT / name / "SKILL.md").is_file()]


def _origin(path: Path) -> str:
    return "builtin" if path.resolve().is_relative_to(BUILTIN_ROOT.resolve()) else "local"


def discover_skills(project: Path | None = None, extra_roots: list[str] | None = None) -> list[dict[str, Any]]:
    """Find SKILL.md metadata in bounded known roots without activation.

    An explicit root may itself be a symlink. Linked skill directories expose
    only their direct SKILL.md; their target subtrees are never traversed.
    Linked SKILL.md files are also accepted.
    The total directory entries inspected are limited to avoid an accidental
    recursive scan of an entire home directory via an overbroad extra root.
    """
    found: dict[str, dict[str, Any]] = {}
    inspected = 0
    for root in _roots(project, extra_roots):
        if not root.is_dir():
            continue
        stack = [(root, 0)]
        while stack:
            directory, depth = stack.pop()
            try:
                entries = sorted(directory.iterdir(), key=lambda p: p.name)
            except OSError:
                continue
            for entry in entries:
                inspected += 1
                if inspected > MAX_DISCOVERY_ENTRIES:
                    raise LocalSkillError("Skill discovery exceeded its bounded entry limit; select narrower skill roots")
                skill_file = None
                if entry.is_symlink():
                    if entry.is_dir() and depth < MAX_DEPTH:
                        direct = entry / "SKILL.md"
                        if direct.is_file():
                            skill_file = direct
                    elif entry.name == "SKILL.md" and entry.is_file():
                        skill_file = entry
                elif entry.is_dir() and depth < MAX_DEPTH:
                    stack.append((entry, depth + 1))
                elif entry.is_file() and entry.name == "SKILL.md":
                    skill_file = entry
                if skill_file is not None:
                    try:
                        # Only the header is required for discovery. A too-large
                        # skill is still discoverable but loading it will fail.
                        with skill_file.open("rb") as handle:
                            header = handle.read(MAX_FILE_BYTES)
                        text = header.decode("utf-8-sig", errors="replace")
                    except OSError:
                        continue
                    path = str(skill_file.resolve())
                    name, description = _metadata(text, skill_file.resolve().parent.name)
                    found[path] = {"name": name, "description": description, "path": path,
                                   "origin": _origin(skill_file),
                                   "suggested_stages": list(STAGE_MAP.get(name, ALL_STAGES))}
    return sorted(found.values(), key=lambda row: (row["name"], row["path"]))


def _explicit_path(selector: str, project: Path) -> Path | None:
    path = Path(selector).expanduser()
    if not path.is_absolute():
        path = project / path
    if path.is_dir():
        return path / "SKILL.md"
    if path.suffix.lower() == ".md" or path.is_absolute() and ("/" in selector or "\\" in selector):
        return path
    if path.is_file():
        return path
    return None


def load_selected_skills(selectors: list[str], project: Path, extra_roots: list[str] | None = None,
                         max_chars: int = 48000) -> list[dict[str, Any]]:
    """Snapshot UTF-8 Markdown selected by exact name or explicit local path.

    Relative paths are relative to ``project``. Duplicate resolved paths are
    loaded once. Ambiguous names and size violations are errors, never silently
    resolved by precedence or truncation. Empty selectors do not scan anything.
    """
    if not isinstance(selectors, list) or any(not isinstance(s, str) or not s.strip() for s in selectors):
        raise LocalSkillError("Skill selectors must be a list of nonempty names or paths")
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars <= 0:
        raise LocalSkillError("max_chars must be a positive integer")
    if not selectors:
        return []
    project = Path(project).expanduser().resolve()
    discovered = None
    resolved: list[Path] = []
    for selector in selectors:
        selected = _explicit_path(selector, project)
        if selected is None:
            if discovered is None:
                discovered = discover_skills(project, extra_roots)
            matches = [row for row in discovered if row["name"] == selector]
            if not matches:
                raise LocalSkillError(f"Skill not found: {selector}; supply its directory or Markdown path")
            if len(matches) > 1:
                paths = ", ".join(row["path"] for row in matches)
                raise LocalSkillError(f"Ambiguous skill name '{selector}'; select one exact path: {paths}")
            selected = Path(matches[0]["path"])
        if selected.suffix.lower() != ".md":
            raise LocalSkillError(f"Skill inputs must be Markdown files: {selected}")
        selected = selected.resolve()
        if not selected.is_file():
            raise LocalSkillError(f"Selected skill file does not exist: {selected}")
        if selected not in resolved:
            resolved.append(selected)
    snapshots: list[dict[str, Any]] = []
    total = 0
    for path in resolved:
        try:
            with path.open("rb") as handle:
                raw = handle.read(MAX_FILE_BYTES + 1)
        except OSError as exc:
            raise LocalSkillError(f"Cannot read selected skill: {path}") from exc
        if len(raw) > MAX_FILE_BYTES:
            raise LocalSkillError(f"Selected skill exceeds 32 KiB; select a smaller explicit reference: {path}")
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeError as exc:
            raise LocalSkillError(f"Selected skill must be UTF-8 Markdown: {path}") from exc
        total += len(content)
        if total > max_chars:
            raise LocalSkillError(f"Selected skill text exceeds max_chars={max_chars}; reduce the selected set")
        fallback = path.parent.name if path.name == "SKILL.md" else path.stem
        name, _ = _metadata(content, fallback)
        snapshots.append({"name": name, "path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                          "content": content, "stages": list(STAGE_MAP.get(name, ALL_STAGES)),
                          "origin": _origin(path)})
    return snapshots
