"""Single source of truth for filesystem layout (ADR-001).

CS2DI_ROOT contains analysis and knowledge; CS2DI_DEMOS_ROOT contains raw replays.
Nothing else in the codebase may hard-code a path.
"""

from __future__ import annotations

from pathlib import Path

from .demo_layout import (
    DEFAULT_DATA_ROOT as DEFAULT_ROOT,  # noqa: F401 (public compatibility alias)
    collection_dir,
    data_root,
    collection_name as collection_name,
    demos_root as demos_root,
    relocated_selection as relocated_selection,
)


def root() -> Path:
    return data_root()


def demos_dir(batch: str) -> Path:
    return collection_dir(batch)


def analysis_dir(batch: str) -> Path:
    return root() / "02_Analysis" / f"analyzed_{batch}"


def outputs_dir() -> Path:
    return root() / "07_Development" / "outputs"
