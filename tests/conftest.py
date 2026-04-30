from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config

# Tests should be deterministic and must not drift into live Claude/Tavily calls
# just because a developer has API keys in their local .env.
config.DEFAULT_CONFIG = config.AppConfig(anthropic_api_key="", tavily_api_key="", opencode_go_api_key="")
