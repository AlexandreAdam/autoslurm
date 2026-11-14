from pathlib import Path
from textwrap import dedent
from typing import Iterable, List, Optional


AGENT_FOLDER = Path(__file__).resolve().parent.parent.parent / "agent"
PACKAGED_AGENT_FOLDER = Path(__file__).resolve().parent / "agent_resources"


def _relative_agent_path(path):
    for folder in (PACKAGED_AGENT_FOLDER, AGENT_FOLDER):
        try:
            return path.relative_to(folder)
        except ValueError:
            continue
    raise ValueError(f"Not an agent resource: {path.name}")


def _ordered_agent_files() -> List[Path]:
    # Packaged recipes have one source of truth; legacy checkout guidance stays
    # available during the staged documentation/distribution refactor.
    files = {_relative_agent_path(path): path
             for folder in (AGENT_FOLDER, PACKAGED_AGENT_FOLDER)
             for path in folder.rglob("*") if path.is_file()}

    def sort_key(path: Path) -> tuple[int, str]:
        name = path.name
        order = 999
        if "_" in name:
            prefix = name.split("_", 1)[0]
            if prefix.isdigit():
                order = int(prefix)
        return order, str(path)

    return sorted(files.values(), key=sort_key)


def _render_file(path: Path) -> str:
    relative = _relative_agent_path(path)
    if path.suffix.lower() == ".md":
        return f"## {relative}\n{path.read_text()}"
    lang = path.suffix.lstrip(".")
    fence = lang if lang else ""
    return f"## {relative}\n```{fence}\n{path.read_text()}```"


def _matches_selectors(path: Path, selectors: Iterable[str]) -> bool:
    rel = _relative_agent_path(path)
    text = str(rel).lower()
    return any(selector.lower() in text for selector in selectors)


def agent_context(sections: Optional[List[str]] = None) -> str:
    """
    Load the agent helpers (project map, examples, etc.) as a single chunk of text.
    """
    ordered = _ordered_agent_files()
    if sections:
        ordered = [
            path for path in ordered if _matches_selectors(path, sections)
        ]
    parts = [_render_file(path) for path in ordered]
    return dedent("\n\n".join(parts)).strip()


def agent_context_paths() -> List[Path]:
    """
    Return a list of agent files that contribute to the context dump.
    """
    return _ordered_agent_files()
