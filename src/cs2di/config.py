"""Single source of truth for filesystem layout (ADR-001).

Set CS2DI_ROOT to the folder that contains ``demos/`` and ``v7dot7Analysis/``.
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
    return root() / "Demos" / batch


def analysis_dir(batch: str) -> Path:
    return root() / "v7dot7Analysis" / f"analyzed_{batch}"


def outputs_dir() -> Path:
    return root() / "Development" / "Outputs"
