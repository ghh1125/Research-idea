"""Report locations: configurable parent, stable timestamp name per project."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .config import load_config


def default_output_root() -> Path:
    # Editable source installs keep outputs next to README even when launched
    # elsewhere. A wheel has no checkout: use the launch directory instead.
    root = Path(__file__).resolve().parents[2]
    if (root / 'pyproject.toml').is_file() and (root / 'src/research_idea').is_dir():
        return root
    return Path.cwd().resolve()


def output_parent(project: Path, config=None) -> Path:
    value = (config if config is not None else load_config(project)).get('output_dir', '')
    if not value:
        return default_output_root()
    path = Path(value).expanduser()
    return (path if path.is_absolute() else project / path).resolve()


def output_directory(store, parent=None) -> Path:
    """Allocate once; a resume/export never invents a second folder name."""
    name = store.get('output_folder')
    if not name:
        name = 'idea-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        store.set('output_folder', name)
    root = Path(parent).expanduser().resolve() if parent is not None else output_parent(store.project)
    return root / name


def saved_report(store) -> Path:
    """Read existing reports without creating directories or modifying state."""
    last = store.get('last_output_dir')
    if last:
        return Path(last) / 'report.md'
    # Old projects remain readable until the next export migrates their reports.
    return store.project / 'outputs' / 'report.md'
