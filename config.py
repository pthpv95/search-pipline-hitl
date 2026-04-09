"""
Centralized runtime configuration for the research pipeline.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

from state import ReportFormat, RunMode


# Approximate Claude API pricing in USD per million tokens.
# Used by evals/eval.py for cost estimation. Update when pricing changes.
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-20250514": {"input_per_million": 3.0, "output_per_million": 15.0},
    "claude-sonnet-4-6": {"input_per_million": 3.0, "output_per_million": 15.0},
    "claude-haiku-4-5-20251001": {"input_per_million": 1.0, "output_per_million": 5.0},
    "claude-opus-4-6": {"input_per_million": 15.0, "output_per_million": 75.0},
}

# Pricing fallback when the configured model isn't in MODEL_PRICING.
DEFAULT_PRICING = {"input_per_million": 3.0, "output_per_million": 15.0}


def get_pricing(model_name: str) -> dict[str, float]:
    """Look up per-million token pricing for a model, falling back to default."""
    return MODEL_PRICING.get(model_name, DEFAULT_PRICING)


class AppConfig(BaseModel):
    mode: RunMode = RunMode.DEV
    model_name: str = "gpt-4o-mini"
    search_provider: str = "tavily"
    report_format: ReportFormat = ReportFormat.DEEP_DIVE
    max_loops: int = 2
    max_retries: int = 2

    # API keys — loaded from env, optional for dev mode
    openai_api_key: str = ""
    tavily_api_key: str = ""

    @classmethod
    def from_env(cls, **overrides) -> "AppConfig":
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
            **overrides,
        )


DEFAULT_CONFIG = AppConfig.from_env()
