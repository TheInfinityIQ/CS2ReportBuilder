"""Raw replay locations, separate from the analysis/knowledge data root.

A copy ships beside standalone extractors; keep the two copies identical.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
DEFAULT_DEMOS_ROOT = DEFAULT_DATA_ROOT / "demos"


def data_root() -> Path:
    return Path(os.environ.get("CS2DI_ROOT", DEFAULT_DATA_ROOT))


def demos_root() -> Path:
    return Path(os.environ.get("CS2DI_DEMOS_ROOT", DEFAULT_DEMOS_ROOT))


def collection_name(folder: Path, analysis_root: Path) -> str:
    """Match a physical player/tournament folder to its existing analysis ID.

    Fail on ambiguous mappings rather than choose another collection's evidence.
    """
    names = [folder.name, folder.name + "_demos"]
    found = [n for n in names if (analysis_root / ("analyzed_" + n)).is_dir()]
    if len(found) > 1:
        raise ValueError(f"Ambiguous analysis collection for {folder}: {found}")
    return found[0] if found else folder.name


def collection_dir(batch: str, raw_root: Path | None = None) -> Path:
    if not batch or Path(batch).name != batch or batch in {".", ".."}:
        raise ValueError("Collection must be one folder name")
    base = raw_root if raw_root is not None else demos_root()
    exact = base / batch
    # Legacy/external layouts retain their literal folder names.
    if exact.is_dir() or not batch.endswith("_demos"):
        return exact
    return base / batch.removesuffix("_demos")


def relocated_selection(folder: Path) -> Path:
    """Translate old saved raw-folder selections; never modify archived records."""
    old = data_root() / "01_Demos"
    try:
        parts = folder.resolve().relative_to(old.resolve()).parts
    except ValueError:
        return folder
    if not parts:
        return demos_root()
    return collection_dir(parts[0]).joinpath(*parts[1:])


def demo_files(folder: Path) -> list[Path]:
    """Recursive raw scan; reject colliding stems before writing any analysis."""
    files = sorted(
        (p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() == ".dem"),
        key=lambda p: str(p).casefold(),
    )
    seen = set()
    for path in files:
        key = path.stem.casefold()
        if key in seen:
            raise ValueError(f"Duplicate demo stem under {folder}: {path.stem}")
        seen.add(key)
    return files
