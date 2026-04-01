"""
Centralized runtime configuration for the research pipeline.
"""

from __future__ import annotations

from pydantic import BaseModel

from state import ReportFormat, RunMode


class AppConfig(BaseModel):
    mode: RunMode = RunMode.DEV
    model_name: str = "stub-model"
    search_provider: str = "stub-search"
    report_format: ReportFormat = ReportFormat.DEEP_DIVE
    max_loops: int = 2


DEFAULT_CONFIG = AppConfig()
