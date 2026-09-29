"""Report rendering: the coach supplies content, the software owns every pixel."""

from .build import build_report
from .plan import PlanError, validate_plan

__all__ = ["build_report", "validate_plan", "PlanError"]
