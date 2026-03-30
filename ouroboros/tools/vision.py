"""
Vision Language Model (VLM) tools for Ouroboros.

Allows the agent to analyze screenshots and images using LLM vision capabilities.
Integrates with the existing browser screenshot workflow:
  browse_page(output='screenshot') → analyze_screenshot() → insight

Two tools:
  - analyze_screenshot: analyze the last browser screenshot using VLM
  - vlm_query: analyze any image (URL or base64) with a custom prompt
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from ouroboros.tools.registry import ToolContext, ToolEntry

log = logging.getLogger(__name__)

_DEFAULT_VLM_MODEL = "anthropic/claude-sonnet-4.6"


def _get_vlm_model() -> str:
    """Get VLM model from env or use default."""
    return os.environ.get("OUROBOROS_VISION_MODEL", _DEFAULT_VLM_MODEL)


def _get_vlm_fallback_models() -> List[str]:
    """Get fallback VLM models list from env (comma-separated)."""
    fallback_str = os.environ.get("OUROBOROS_VISION_MODEL_FALLBACK_LIST", "")
    if not fallback_str:
        return []
    return [m.strip() for m in fallback_str.split(",") if m.strip()]


def _get_llm_client():
    """Lazy-import LLMClient to avoid circular imports."""
    from ouroboros.llm import LLMClient
    return LLMClient()


def _call_vlm_with_fallback(
    ctx: ToolContext,
    prompt: str,
    images: List[Dict[str, Any]],
    primary_model: str = "",
    max_tokens: int = 1024,
    reasoning_effort: str = "low",
) -> str:
    """
    Call VLM with fallback logic. Tries primary model first; if empty response,
    iterates through fallback list until a non-empty response is obtained.

    Returns the first non-empty response, or error message if all fail.
    """
    vlm_model = primary_model or _get_vlm_model()
    fallback_models = _get_vlm_fallback_models()
    client = _get_llm_client()

    # Attempt primary model
    try:
        text, usage = client.vision_query(
            prompt=prompt,
            images=images,
            model=vlm_model,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
        )
        _emit_usage(ctx, usage, vlm_model)
        if text and text.strip():
            return text
        log.info("VLM primary model returned empty, trying fallback (if any)")
    except Exception as e:
        log.warning("VLM primary model failed: %s", e, exc_info=True)

    # Try fallbacks sequentially
    for fallback_model in fallback_models:
        try:
            text, usage = client.vision_query(
                prompt=prompt,
                images=images,
                model=fallback_model,
                max_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
            )
            _emit_usage(ctx, usage, fallback_model)
            if text and text.strip():
                log.info("VLM fallback succeeded with %s", fallback_model)
                return text
            log.info("VLM fallback %s returned empty, trying next...", fallback_model)
        except Exception as e:
            log.warning("VLM fallback %s failed: %s", fallback_model, e, exc_info=True)

    return "(no response from VLM — all models failed)"


def _analyze_screenshot(
    ctx: ToolContext,
    prompt: str = "Describe what you see in this screenshot. Note any important UI elements, text, errors, or visual issues.",
    model: str = "",
) -> str:
    """
    Analyze the last browser screenshot using a Vision LLM with fallback.

    Requires a prior browse_page(output='screenshot') or browser_action(action='screenshot').
    """
    b64 = ctx.browser_state.last_screenshot_b64
    if not b64:
        return (
            "⚠️ No screenshot available. "
            "First call browse_page(output='screenshot') or browser_action(action='screenshot')."
        )

    images = [{"base64": b64, "mime": "image/png"}]
    return _call_vlm_with_fallback(
        ctx=ctx,
        prompt=prompt,
        images=images,
        primary_model=model,
    )


def _vlm_query(
    ctx: ToolContext,
    prompt: str,
    image_url: str = "",
    image_base64: str = "",
    image_mime: str = "image/png",
    model: str = "",
) -> str:
    """
    Analyze any image using a Vision LLM with fallback. Provide either image_url or image_base64.
    """
    if not image_url and not image_base64:
        return "⚠️ Provide either image_url or image_base64."

    images: List[Dict[str, Any]] = []
    if image_url:
        images.append({"url": image_url})
    else:
        images.append({"base64": image_base64, "mime": image_mime})

    return _call_vlm_with_fallback(
        ctx=ctx,
        prompt=prompt,
        images=images,
        primary_model=model,
    )


def _emit_usage(ctx: ToolContext, usage: Dict[str, Any], model: str) -> None:
    """Emit LLM usage event for budget tracking."""
    if ctx.event_queue is None:
        return
    try:
        event = {
            "type": "llm_usage",
            "model": model,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "cached_tokens": usage.get("cached_tokens", 0),
            "cost": usage.get("cost", 0.0),
            "task_id": ctx.task_id,
            "task_type": ctx.current_task_type or "task",
        }
        ctx.event_queue.put_nowait(event)
    except Exception:
        log.debug("Failed to emit VLM usage event", exc_info=True)


def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry(
            name="analyze_screenshot",
            schema={
                "name": "analyze_screenshot",
                "description": (
                    "Analyze the last browser screenshot using a Vision LLM with automatic fallback. "
                    "Must call browse_page(output='screenshot') or browser_action(action='screenshot') first. "
                    "Returns a text description and analysis of the screenshot. "
                    "Use this to verify UI, check for visual errors, or understand page layout."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "What to look for or analyze in the screenshot (default: general description)",
                        },
                        "model": {
                            "type": "string",
                            "description": "VLM model to use as primary (default: OUROBOROS_VISION_MODEL)",
                        },
                    },
                    "required": [],
                },
            },
            handler=_analyze_screenshot,
            timeout_sec=30,
        ),
        ToolEntry(
            name="vlm_query",
            schema={
                "name": "vlm_query",
                "description": (
                    "Analyze any image using a Vision LLM with automatic fallback. "
                    "Provide either image_url (public URL) or image_base64 (base64-encoded PNG/JPEG). "
                    "Use for: analyzing charts, reading diagrams, understanding screenshots, checking UI."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "What to analyze or describe about the image",
                        },
                        "image_url": {
                            "type": "string",
                            "description": "Public URL of the image to analyze",
                        },
                        "image_base64": {
                            "type": "string",
                            "description": "Base64-encoded image data",
                        },
                        "image_mime": {
                            "type": "string",
                            "description": "MIME type for base64 image (default: image/png)",
                        },
                        "model": {
                            "type": "string",
                            "description": "VLM model to use as primary (default: OUROBOROS_VISION_MODEL)",
                        },
                    },
                    "required": ["prompt"],
                },
            },
            handler=_vlm_query,
            timeout_sec=30,
        ),
    ]
