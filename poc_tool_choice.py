"""Test if the OpenCode Go proxy passes tool_choice correctly."""
import os
import sys

from dotenv import load_dotenv
from pydantic import BaseModel
from langchain_openai import ChatOpenAI


load_dotenv()

# --- Config from env ---
API_KEY = os.getenv("OPENCODE_GO_API_KEY", "")
BASE_URL = os.getenv("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1")
MODEL = os.getenv("OPENCODE_GO_MODEL", "glm-5")

if not API_KEY:
    print("FAIL: OPENCODE_GO_API_KEY is not set. Add it to .env or export it in your shell.")
    sys.exit(1)

# --- Define a simple tool (same pattern as all 3 agents) ---
class GreetingOutput(BaseModel):
    greeting: str
    language: str


print(f"Testing tool_choice via {BASE_URL} with model {MODEL}")

# --- Test with forced tool_choice ---
llm = ChatOpenAI(
    model=MODEL,
    api_key=API_KEY,
    base_url=BASE_URL,
    temperature=0,
)
llm_with_tool = llm.bind_tools(
    [GreetingOutput],
    tool_choice={"type": "function", "function": {"name": "GreetingOutput"}},
)
response = llm_with_tool.invoke("Say hello in French")
# --- Verify ---
tc = getattr(response, "tool_calls", None)
if tc and len(tc) > 0:
    call = tc[0]
    print(f"PASS: tool_choice works")
    print(f"  tool called: {call['name']}")
    print(f"  args: {call['args']}")
else:
    print(f"FAIL: No tool call returned")
    print(f"  response content: {str(response.content)[:200]}")
    sys.exit(1)
