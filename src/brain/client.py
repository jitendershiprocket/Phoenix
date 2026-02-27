"""Opus 4.6 API Client for code analysis and fix generation."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

# Anthropic SDK
try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None


def _load_brain_config() -> dict:
    """Load brain config from settings.yaml."""
    config_path = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
            return data.get("brain", {})
    return {}


def call_opus(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.2,
) -> str:
    """
    Call Anthropic Opus 4.6 (or configured model).
    Returns the assistant's text response.
    """
    if Anthropic is None:
        raise ImportError("anthropic package required. pip install anthropic")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable required")

    config = _load_brain_config()
    model = model or config.get("model", "claude-opus-4-6")
    max_tokens = max_tokens or config.get("max_tokens", 4096)
    temperature = temperature if temperature is not None else config.get("temperature", 0.2)

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text
    return text
