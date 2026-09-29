"""Single source of truth for filesystem layout (ADR-001).

Set CS2DI_ROOT to the folder that contains ``01_Demos/`` and ``02_Analysis/`` (layout in 00_LEGEND.md).
Nothing else in the codebase may hard-code a path.
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ROOT = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive"
    r"\game\csgo\replays\demoparser"
)


def root() -> Path:
    return Path(os.environ.get("CS2DI_ROOT", DEFAULT_ROOT))


def demos_dir(batch: str) -> Path:
    return root() / "01_Demos" / batch


def analysis_dir(batch: str) -> Path:
    return root() / "02_Analysis" / f"analyzed_{batch}"


def outputs_dir() -> Path:
    return root() / "07_Development" / "outputs"
