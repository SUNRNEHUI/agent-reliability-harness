#!/usr/bin/env python3
"""Runtime-specific model profile maps kept outside the portable core schema."""

from __future__ import annotations

from harness_schema import LEGACY_MODEL_ROUTING_POLICY, MODEL_ROUTING_POLICY


SUPPORTED_MODEL_RUNTIMES = {"codex", "grok"}

CODEX_MODEL_PROFILES = {
    "fast": {"model": "gpt-5.6-luna", "reasoning_effort": "max"},
    "main": {"model": "gpt-5.6-luna", "reasoning_effort": "max"},
    "planner": {"model": "gpt-5.6-sol", "reasoning_effort": "max"},
    "critical_reviewer": {"model": "gpt-5.6-sol", "reasoning_effort": "max"},
}

GROK_MODEL_PROFILES = {
    "fast": {"model": "grok-api", "reasoning_effort": "low"},
    "main": {"model": "grok-api", "reasoning_effort": "high"},
    "planner": {"model": "grok-api", "reasoning_effort": "high"},
    "critical_reviewer": {"model": "grok-api", "reasoning_effort": "xhigh"},
}

LEGACY_CODEX_MODEL_PROFILES = {
    "fast": {"model": "gpt-5.6-luna", "reasoning_effort": "medium"},
    "main": {"model": "gpt-5.6-luna", "reasoning_effort": "xhigh"},
    "planner": {"model": "gpt-5.6-sol", "reasoning_effort": "high"},
    "critical_reviewer": {"model": "gpt-5.6-sol", "reasoning_effort": "xhigh"},
}

RUNTIME_MODEL_PROFILES = {
    "codex": CODEX_MODEL_PROFILES,
    "grok": GROK_MODEL_PROFILES,
}

RUNTIME_MODEL_PROFILES_BY_POLICY = {
    MODEL_ROUTING_POLICY: RUNTIME_MODEL_PROFILES,
    LEGACY_MODEL_ROUTING_POLICY: {
        "codex": LEGACY_CODEX_MODEL_PROFILES,
        "grok": GROK_MODEL_PROFILES,
    },
}


def model_profiles_for(
    runtime: str,
    routing_policy: str | None = MODEL_ROUTING_POLICY,
) -> dict[str, dict[str, str]] | None:
    """Return a copy of the runtime profiles sealed by a routing policy."""
    policy_profiles = RUNTIME_MODEL_PROFILES_BY_POLICY.get(routing_policy)
    if policy_profiles is None:
        return None
    profiles = policy_profiles.get((runtime or "").strip().casefold())
    if profiles is None:
        return None
    return {name: dict(config) for name, config in profiles.items()}
