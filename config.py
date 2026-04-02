"""
Centralized runtime configuration for the research pipeline.
"""

from __future__ import annotations

import os

from pydantic import BaseModel

from state import ReportFormat, RunMode


class AppConfig(BaseModel):
    mode: RunMode = RunMode.DEV
    model_name: str = "claude-sonnet-4-20250514"
    search_provider: str = "tavily"
    report_format: ReportFormat = ReportFormat.DEEP_DIVE
    max_loops: int = 2
    max_retries: int = 2

    # API keys — loaded from env, optional for dev mode
    anthropic_api_key: str = ""
    tavily_api_key: str = ""

    @classmethod
    def from_env(cls, **overrides) -> "AppConfig":
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
            **overrides,
        )


DEFAULT_CONFIG = AppConfig.from_env()
