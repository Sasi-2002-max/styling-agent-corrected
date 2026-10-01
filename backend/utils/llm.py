"""
Central LLM communication layer for the AI Fashion Stylist.

All communication with the Groq LLM happens through this file.

Agents should NOT create their own Groq clients.

They should call:
    generate_text()
    generate_json()
    generate_with_tools()

The tool-calling flow is intentionally separated from the final JSON
generation flow. This prevents the model from confusing "JSON output"
with a callable tool named "json".
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from groq import Groq


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

class LLMConfigurationError(RuntimeError):
    """Raised when the LLM is called without its required configuration."""


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

# Override this in .env if desired.
#
# Recommended current Groq model:
#   openai/gpt-oss-120b
#
# Do not default to the deprecated llama-3.3-70b-versatile.
GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-120b",
)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

client: Optional[Groq] = None


def _get_client() -> Groq:
    """Create the Groq client only when an LLM request is actually made."""
    global client
    if client is not None:
        return client

    api_key = GROQ_API_KEY or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise LLMConfigurationError(
            "GROQ_API_KEY is not configured. Add it through Replit Secrets."
        )
    client = Groq(api_key=api_key)
    return client


# ---------------------------------------------------------------------------
# Plain text generation
# ---------------------------------------------------------------------------

def generate_text(prompt: str) -> str:
    """
    Send a normal text-generation request to Groq.
    """

    response = _get_client().chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# JSON generation
# ---------------------------------------------------------------------------

def generate_json(
    messages: List[Dict[str, Any]],
) -> str:
    """
    Generate a JSON object using Groq JSON Object Mode.

    IMPORTANT:
    This request deliberately does NOT contain tools.

    The stylist agent first completes any fashion-knowledge tool calls.
    Only after that does it call this function to produce the final
    OutfitPlan JSON.

    This prevents the model from interpreting "json" as a tool name.
    """

    response = _get_client().chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        response_format={
            "type": "json_object",
        },
    )

    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Tool calling
# ---------------------------------------------------------------------------

def generate_with_tools(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    tool_choice: str = "auto",
):
    """
    Send a conversation to Groq with tool definitions.

    This function is ONLY for the tool-calling phase.

    It does not request JSON mode.

    The caller is responsible for:
      1. receiving the assistant tool call
      2. executing the tool
      3. appending the assistant message
      4. appending the tool result
      5. deciding when to switch to generate_json()
    """

    response = _get_client().chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        tools=tools,
        tool_choice=tool_choice,
    )

    return response.choices[0].message