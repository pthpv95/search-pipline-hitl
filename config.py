"""
Centralized runtime configuration for the research pipeline.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

from state import ReportFormat, RunMode  # noqa: E402

# Approximate model pricing in USD per million tokens.
# Used by evals/eval.py for cost estimation. Update when pricing changes.
MODEL_PRICING: dict[str, dict[str, float]] = {
    # Anthropic
    "claude-sonnet-4-20250514": {"input_per_million": 3.0, "output_per_million": 15.0},
    "claude-sonnet-4-6": {"input_per_million": 3.0, "output_per_million": 15.0},
    "claude-haiku-4-5-20251001": {"input_per_million": 1.0, "output_per_million": 5.0},
    "claude-opus-4-6": {"input_per_million": 15.0, "output_per_million": 75.0},
    # OpenCode Go (Zen docs pricing)
    "glm-5":   {"input_per_million": 1.00, "output_per_million": 3.20},
    "glm-5.1": {"input_per_million": 1.40, "output_per_million": 4.40},
    "kimi-k2.5": {"input_per_million": 0.60, "output_per_million": 3.00},
    "kimi-k2.6": {"input_per_million": 0.95, "output_per_million": 4.00},
    "qwen3.5-plus": {"input_per_million": 0.20, "output_per_million": 1.20},
    "qwen3.6-plus": {"input_per_million": 0.50, "output_per_million": 3.00},
    "deepseek-v4-pro": {"input_per_million": 0.27, "output_per_million": 1.10},
    "deepseek-v4-flash": {"input_per_million": 0.27, "output_per_million": 1.10},
}

# Pricing fallback when the configured model isn't in MODEL_PRICING.
DEFAULT_PRICING = {"input_per_million": 3.0, "output_per_million": 15.0}


def get_pricing(model_name: str) -> dict[str, float]:
    """Look up per-million token pricing for a model, falling back to default."""
    return MODEL_PRICING.get(model_name, DEFAULT_PRICING)


class AppConfig(BaseModel):
    mode: RunMode = RunMode.DEV
    llm_provider: str = "anthropic"        # "anthropic" | "opencode_go"
    model_name: str = "claude-sonnet-4-20250514"  # used when provider=anthropic
    search_provider: str = "tavily"
    report_format: ReportFormat = ReportFormat.DEEP_DIVE
    max_loops: int = 2
    max_retries: int = 2

    # Anthropic
    anthropic_api_key: str = ""
    # OpenCode Go
    opencode_go_api_key: str = ""
    opencode_go_base_url: str = "https://opencode.ai/zen/go/v1"
    opencode_go_model: str = "glm-5"
    # Tavily
    tavily_api_key: str = ""

    @property
    def effective_model_name(self) -> str:
        """The model name being used given the current provider."""
        if self.llm_provider == "opencode_go":
            return self.opencode_go_model
        return self.model_name

    @classmethod
    def from_env(cls, **overrides) -> AppConfig:
        return cls(
            llm_provider=os.getenv("LLM_PROVIDER", "anthropic"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
            opencode_go_api_key=os.getenv("OPENCODE_GO_API_KEY", ""),
            opencode_go_base_url=os.getenv("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1"),
            opencode_go_model=os.getenv("OPENCODE_GO_MODEL", "glm-5"),
            **overrides,
        )


DEFAULT_CONFIG = AppConfig.from_env()
