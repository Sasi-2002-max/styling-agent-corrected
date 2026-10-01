"""
Stylist Agent.

Turns a Profile Agent's style_context, the user's original query, and
fashion knowledge into a structured OutfitPlan.

This module decides WHAT the outfit should contain.

It does NOT:
- search real products
- call the Shopping Agent
- call MCP shopping tools
- create avatars
- create fitting-room images
- access the database

All LLM communication goes through backend.utils.llm.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from backend.agents.state import AgentState
from backend.rag.tools import (
    RETRIEVE_FASHION_KNOWLEDGE_TOOL,
    retrieve_fashion_knowledge,
)
from backend.schemas.outfit import OutfitPlan
from backend.utils.llm import (
    LLMConfigurationError,
    generate_text,
    generate_with_tools,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_TOOL_CALLS = 5


class StylistAgentError(Exception):
    """Raised when the Stylist Agent cannot produce a valid OutfitPlan."""


class StylistToolLoopLimitError(StylistAgentError):
    """
    Raised when the model keeps requesting tools beyond MAX_TOOL_CALLS.

    This is intentionally NOT converted into a fallback response because
    reaching the loop limit indicates a workflow/control-flow problem that
    should remain visible to tests and callers.
    """


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are an expert fashion stylist creating one complete outfit recommendation.

You will be given:

- USER PROFILE: known attributes about the user's body and appearance.
- USER REQUIREMENTS: structured requirements extracted from the user's request.
- USER QUERY: the user's original natural-language request.

Your job is to create a complete, coherent outfit.

Rules:

1. Match the stated occasion and formality.
2. Use body shape, skin tone, height and weight only as general styling
   information for visual balance and color coordination.
3. Never make judgments about the user's body or appearance.
4. Only use style or fit preferences that the user explicitly stated.
5. Never invent preferences.
6. Respect the stated budget when a budget exists.
7. Make the outfit coherent.
8. A complete outfit should normally contain:
   - a top/bottom combination OR a dress,
   - appropriate footwear,
   - optional accessories.
9. Accessories are optional.
10. Do not recommend real products or product IDs.
11. Do not search shopping websites.
12. Do not call shopping/MCP tools.
13. If fashion knowledge is required, the ONLY available fashion tool is:
    retrieve_fashion_knowledge.
14. Never attempt to call a tool named "json", "JSON", "python", "search",
    "shopping", or any other unavailable tool.
15. Your final answer must be a single JSON object matching the OutfitPlan
    schema.
16. Do not wrap the final JSON in markdown fences.
17. Do not put commentary before or after the JSON.

The JSON schema is:

{schema}
"""


TOOL_GUIDANCE = """
You may use the fashion knowledge retrieval tool when additional fashion
knowledge would improve the outfit.

The ONLY allowed tool is:

retrieve_fashion_knowledge

Use it only for fashion knowledge such as:

- color coordination
- skin tone
- body shape
- occasion
- formality
- fit
- silhouettes
- styling principles

Do NOT use it for:

- products
- prices
- shopping websites
- MCP
- product availability

Never call a tool named "json" or any other unavailable tool.

After receiving any required fashion knowledge, produce the final
OutfitPlan as JSON.
"""


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_profile(profile: Dict[str, Any]) -> str:
    """Render profile information as readable lines."""
    if not profile:
        return "No profile details were provided."

    lines: List[str] = []

    for key, value in profile.items():
        label = str(key).replace("_", " ").title()
        lines.append(f"{label}: {value}")

    return "\n".join(lines)


def _format_requirements(requirements: Dict[str, Any]) -> str:
    """Render structured requirements as readable text."""
    occasion = requirements.get("occasion") or "Not specified"
    formality = requirements.get("formality") or "Not specified"
    budget = requirements.get("budget")

    budget_line = (
        "Not specified"
        if budget is None
        else f"₹{budget}"
    )

    style_preferences = requirements.get("style_preferences") or []
    fit_preferences = requirements.get("fit_preferences") or []

    return "\n".join(
        [
            f"Occasion: {occasion}",
            f"Formality: {formality}",
            f"Budget: {budget_line}",
            "Style preferences: "
            + (
                ", ".join(map(str, style_preferences))
                if style_preferences
                else "None stated"
            ),
            "Fit preferences: "
            + (
                ", ".join(map(str, fit_preferences))
                if fit_preferences
                else "None stated"
            ),
        ]
    )


def _format_rag_context(
    rag_context: Optional[List[str]],
) -> str:
    """Render manually supplied RAG passages."""
    if not rag_context:
        return "No additional fashion knowledge context was provided."

    lines: List[str] = [
        "FASHION KNOWLEDGE:",
        "",
    ]

    for index, passage in enumerate(rag_context, start=1):
        lines.append(f"[Document {index}]")
        lines.append(str(passage).strip())
        lines.append("")

    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_system_prompt(
    *,
    include_tool_guidance: bool = False,
) -> str:
    """Build the Stylist Agent system prompt."""
    schema = json.dumps(
        OutfitPlan.model_json_schema(),
        indent=2,
    )

    prompt = SYSTEM_PROMPT.format(schema=schema)

    if include_tool_guidance:
        prompt += "\n" + TOOL_GUIDANCE

    return prompt


def _build_user_prompt(
    profile: Dict[str, Any],
    requirements: Dict[str, Any],
    user_query: str,
    rag_context: Optional[List[str]],
) -> str:
    """Build the legacy/manual-RAG prompt."""
    return (
        f"USER PROFILE:\n{_format_profile(profile)}\n\n"
        f"USER REQUIREMENTS:\n{_format_requirements(requirements)}\n\n"
        f'USER QUERY:\n"{user_query.strip()}"\n\n'
        f"FASHION KNOWLEDGE:\n"
        f"{_format_rag_context(rag_context)}\n"
    )


def _build_user_prompt_for_tools(
    profile: Dict[str, Any],
    requirements: Dict[str, Any],
    user_query: str,
) -> str:
    """Build the tool-calling user prompt."""
    return (
        f"USER PROFILE:\n{_format_profile(profile)}\n\n"
        f"USER REQUIREMENTS:\n{_format_requirements(requirements)}\n\n"
        f'USER QUERY:\n"{user_query.strip()}"\n'
    )


def _build_fallback_prompt(
    profile: Dict[str, Any],
    requirements: Dict[str, Any],
    user_query: str,
) -> str:
    """Build a strict non-tool generation prompt."""
    schema = json.dumps(
        OutfitPlan.model_json_schema(),
        indent=2,
    )

    return f"""
Create one complete outfit from the information below.

USER PROFILE:
{_format_profile(profile)}

USER REQUIREMENTS:
{_format_requirements(requirements)}

USER QUERY:
"{user_query.strip()}"

IMPORTANT:

- Do not call any tools.
- Return ONLY one JSON object.
- Do not use markdown.
- Do not add commentary.
- Do not invent products.
- Do not invent product IDs.
- Respect the user's explicit requirements.
- Respect the user's stated budget.
- Respect explicitly stated style and fit preferences.
- Create a coherent complete outfit.
- Include a short user-facing reasoning field.

OUTFIT PLAN SCHEMA:

{schema}
""".strip()


# ---------------------------------------------------------------------------
# style_context validation
# ---------------------------------------------------------------------------

def _extract_profile_and_requirements(
    style_context: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Extract profile and requirements from Profile Agent output."""

    if not isinstance(style_context, dict):
        raise StylistAgentError(
            "style_context is missing or invalid. "
            "Run the Profile Agent first and pass its output as style_context."
        )

    requirements = style_context.get("requirements")

    if not isinstance(requirements, dict):
        raise StylistAgentError(
            "style_context is missing 'requirements'. "
            "Run the Profile Agent first and pass its output as style_context."
        )

    profile = style_context.get("profile")

    if not isinstance(profile, dict):
        logger.warning(
            "style_context has no usable 'profile'; "
            "continuing without profile information."
        )
        profile = {}

    return profile, requirements


# ---------------------------------------------------------------------------
# Plain LLM call
# ---------------------------------------------------------------------------

def _call_llm(
    system_prompt: str,
    user_prompt: str,
) -> str:
    """Call the centralized plain-text LLM helper."""

    combined_prompt = (
        f"{system_prompt}\n\n"
        f"{user_prompt}"
    )

    try:
        return generate_text(combined_prompt)
    except LLMConfigurationError:
        raise
    except Exception as exc:
        raise StylistAgentError(
            f"Stylist Agent could not reach the LLM: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

def _execute_tool_call(
    tool_call: Any,
) -> str:
    """
    Execute a tool requested by the LLM.

    Only retrieve_fashion_knowledge is permitted.
    """

    function = getattr(tool_call, "function", None)

    function_name = getattr(
        function,
        "name",
        "",
    )

    raw_arguments = getattr(
        function,
        "arguments",
        "",
    ) or "{}"

    if function_name != "retrieve_fashion_knowledge":
        logger.error(
            "LLM attempted to call an unsupported tool: %s",
            function_name,
        )

        return (
            "Unsupported tool requested. "
            "Only retrieve_fashion_knowledge is available. "
            "Continue by producing the final OutfitPlan."
        )

    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError:
        logger.warning(
            "Could not parse arguments for retrieve_fashion_knowledge: %r",
            raw_arguments,
        )
        arguments = {}

    query = str(
        arguments.get("query", "")
    ).strip()

    if not query:
        return "No fashion knowledge query was supplied."

    top_k_raw = arguments.get("top_k", 5)

    try:
        top_k = int(top_k_raw)
    except (TypeError, ValueError):
        top_k = 5

    top_k = max(1, min(top_k, 10))

    logger.info(
        "Stylist LLM requested fashion knowledge: %s",
        query,
    )

    try:
        results = retrieve_fashion_knowledge(
            query=query,
            top_k=top_k,
        )
    except Exception:
        logger.exception(
            "Fashion knowledge retrieval failed."
        )

        return (
            "Fashion knowledge retrieval failed. "
            "Continue without additional knowledge and "
            "produce the OutfitPlan."
        )

    if not results:
        return "No relevant fashion knowledge was found."

    return "\n\n".join(
        str(result)
        for result in results
    )


# ---------------------------------------------------------------------------
# Safe assistant-message conversion
# ---------------------------------------------------------------------------

def _assistant_message_to_dict(
    message: Any,
) -> Dict[str, Any]:
    """
    Convert the Groq SDK assistant message into a normal dictionary.

    This ensures the next API request receives JSON-compatible data.
    """

    result: Dict[str, Any] = {
        "role": "assistant",
        "content": getattr(
            message,
            "content",
            None,
        ),
    }

    tool_calls = getattr(
        message,
        "tool_calls",
        None,
    )

    if tool_calls:
        serialized_tool_calls: List[Dict[str, Any]] = []

        for tool_call in tool_calls:
            function = getattr(
                tool_call,
                "function",
                None,
            )

            serialized_tool_calls.append(
                {
                    "id": getattr(
                        tool_call,
                        "id",
                        "",
                    ),
                    "type": "function",
                    "function": {
                        "name": getattr(
                            function,
                            "name",
                            "",
                        ),
                        "arguments": getattr(
                            function,
                            "arguments",
                            "{}",
                        ),
                    },
                }
            )

        result["tool_calls"] = serialized_tool_calls

    return result


# ---------------------------------------------------------------------------
# Tool-calling loop
# ---------------------------------------------------------------------------

def _run_tool_calling_loop(
    system_prompt: str,
    user_prompt: str,
) -> str:
    """
    Run the fashion knowledge tool-calling loop.

    Raises:
        StylistToolLoopLimitError:
            If the model keeps requesting tools indefinitely.

        StylistAgentError:
            If the LLM request fails or returns an unusable response.
    """

    messages: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]

    tools = [
        RETRIEVE_FASHION_KNOWLEDGE_TOOL
    ]

    for iteration in range(MAX_TOOL_CALLS):
        logger.info(
            "Stylist LLM tool-calling iteration %d/%d",
            iteration + 1,
            MAX_TOOL_CALLS,
        )

        try:
            message = generate_with_tools(
                messages,
                tools=tools,
                tool_choice="auto",
            )
        except LLMConfigurationError:
            raise
        except Exception as exc:
            raise StylistAgentError(
                f"Tool-calling request failed: {exc}"
            ) from exc

        tool_calls = getattr(
            message,
            "tool_calls",
            None,
        )

        if not tool_calls:
            content = (
                getattr(
                    message,
                    "content",
                    None,
                )
                or ""
            )

            if content.strip():
                return content

            raise StylistAgentError(
                "Stylist LLM returned an empty response."
            )

        # Convert SDK object into a JSON-compatible assistant message.
        messages.append(
            _assistant_message_to_dict(message)
        )

        for tool_call in tool_calls:
            tool_name = getattr(
                getattr(
                    tool_call,
                    "function",
                    None,
                ),
                "name",
                "",
            )

            tool_content = _execute_tool_call(
                tool_call
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": getattr(
                        tool_call,
                        "id",
                        "",
                    ),
                    "name": tool_name,
                    "content": tool_content,
                }
            )

    # IMPORTANT:
    # Do NOT convert this into a normal StylistAgentError.
    # The tests and workflow need to know that the model exceeded the
    # allowed tool-call loop.
    raise StylistToolLoopLimitError(
        "Stylist Agent exceeded the maximum "
        f"of {MAX_TOOL_CALLS} tool-calling iterations."
    )


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

_JSON_FENCE_PATTERN = re.compile(
    r"```(?:json)?\s*(\{.*\})\s*```",
    re.DOTALL | re.IGNORECASE,
)


def _extract_json_block(
    raw_text: str,
) -> str:
    """Extract a JSON object from LLM output."""

    if not raw_text:
        return ""

    text = raw_text.strip()

    fenced = _JSON_FENCE_PATTERN.search(text)

    if fenced:
        return fenced.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]

    return text


def _parse_outfit_plan(
    raw_text: str,
) -> OutfitPlan:
    """Parse and validate the LLM output as OutfitPlan."""

    json_block = _extract_json_block(raw_text)

    if not json_block:
        raise StylistAgentError(
            "The stylist LLM returned an empty response."
        )

    try:
        data = json.loads(json_block)
    except json.JSONDecodeError as exc:
        raise StylistAgentError(
            "The stylist LLM did not return valid JSON: "
            f"{exc}"
        ) from exc

    try:
        return OutfitPlan.model_validate(data)
    except ValidationError as exc:
        raise StylistAgentError(
            "The stylist LLM's output did not match "
            f"the OutfitPlan schema: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Safe fallback generation
# ---------------------------------------------------------------------------

def _run_safe_fallback(
    profile: Dict[str, Any],
    requirements: Dict[str, Any],
    user_query: str,
) -> OutfitPlan:
    """
    Generate an OutfitPlan without tool calling.

    This is used for recoverable tool/API failures such as a model attempting
    to call an unavailable tool such as "json".
    """

    logger.warning(
        "Using Stylist Agent safe fallback without tool calling."
    )

    schema = json.dumps(
        OutfitPlan.model_json_schema(),
        indent=2,
    )

    system_prompt = f"""
You are the AI Fashion Stylist's final structured-output generator.

Do not call tools.

Return ONLY one JSON object matching the supplied OutfitPlan schema.

Do not use markdown.
Do not add commentary.
Do not invent products or product IDs.
Respect the user's explicit requirements and budget.
Respect explicitly stated style and fit preferences.
Create a coherent complete outfit.
Include a short user-facing reasoning field.

OutfitPlan schema:

{schema}
""".strip()

    user_prompt = _build_fallback_prompt(
        profile,
        requirements,
        user_query,
    )

    raw_output = _call_llm(
        system_prompt,
        user_prompt,
    )

    return _parse_outfit_plan(
        raw_output
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_outfit_plan(
    style_context: Dict[str, Any],
    user_query: str,
    rag_context: Optional[List[str]] = None,
) -> OutfitPlan:
    """
    Produce a validated OutfitPlan.

    Normal path:
        Profile context
            ->
        Stylist LLM
            ->
        optional fashion knowledge retrieval
            ->
        OutfitPlan

    Recoverable tool/API failures:
        tool-calling failure
            ->
        safe non-tool generation

    Non-recoverable control-flow failure:
        MAX_TOOL_CALLS exceeded
            ->
        StylistToolLoopLimitError is propagated
    """

    profile, requirements = (
        _extract_profile_and_requirements(
            style_context
        )
    )

    user_query = user_query or ""

    # ---------------------------------------------------------------
    # Legacy manually supplied RAG path
    # ---------------------------------------------------------------

    if rag_context is not None:
        logger.info(
            "rag_context supplied manually; "
            "using legacy single-call path."
        )

        system_prompt = _build_system_prompt(
            include_tool_guidance=False
        )

        user_prompt = _build_user_prompt(
            profile,
            requirements,
            user_query,
            rag_context,
        )

        raw_output = _call_llm(
            system_prompt,
            user_prompt,
        )

        return _parse_outfit_plan(
            raw_output
        )

    # ---------------------------------------------------------------
    # Normal tool-calling path
    # ---------------------------------------------------------------

    system_prompt = _build_system_prompt(
        include_tool_guidance=True
    )

    user_prompt = _build_user_prompt_for_tools(
        profile,
        requirements,
        user_query,
    )

    try:
        raw_output = _run_tool_calling_loop(
            system_prompt,
            user_prompt,
        )

        return _parse_outfit_plan(
            raw_output
        )

    except StylistToolLoopLimitError:
        # IMPORTANT:
        # This is deliberately re-raised.
        #
        # The model has exceeded the safety limit. Hiding this behind the
        # fallback would make the control-flow test fail and would conceal
        # a potentially problematic model/tool loop.
        raise

    except StylistAgentError as exc:
        # Recoverable failures such as Groq tool validation errors can use
        # the non-tool structured-generation path.
        logger.warning(
            "Stylist tool-calling path failed. "
            "Falling back to safe structured generation. "
            "Reason: %s",
            exc,
        )

        return _run_safe_fallback(
            profile,
            requirements,
            user_query,
        )


# ---------------------------------------------------------------------------
# Workflow wrapper
# ---------------------------------------------------------------------------

def stylist_agent(
    state: AgentState,
) -> AgentState:
    """
    Workflow-facing Stylist Agent.

    Reads:
        state["style_context"]
        state["user_query"]
        state["rag_context"]

    Writes:
        state["outfit_plan"]
    """

    style_context = (
        state.get("style_context")
        or {}
    )

    user_query = (
        state.get("user_query")
        or ""
    )

    rag_context = (
        state.get("rag_context")
        or None
    )

    plan = create_outfit_plan(
        style_context=style_context,
        user_query=user_query,
        rag_context=rag_context,
    )

    state["outfit_plan"] = plan.model_dump()

    return state


# ---------------------------------------------------------------------------
# Local test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    sample_style_context = {
        "profile": {
            "age": 24,
            "gender": "Female",
            "body_shape": "rectangle",
            "skin_tone": "warm",
            "height": 165,
            "weight": 55,
        },
        "requirements": {
            "occasion": "casual",
            "formality": "casual",
            "budget": 1500,
            "style_preferences": [],
            "fit_preferences": [],
        },
    }

    sample_user_query = (
        "I need a black shirt under ₹1500, size M"
    )

    print("Stylist Agent started\n")

    try:
        result = create_outfit_plan(
            style_context=sample_style_context,
            user_query=sample_user_query,
        )

        print("\nFinal OutfitPlan:")
        print(
            result.model_dump_json(
                indent=4
            )
        )

    except StylistAgentError as error:
        print(
            f"Stylist Agent failed: {error}"
        )