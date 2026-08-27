#!/usr/bin/env python3
"""Select a progress-bounded model profile from observable task signals."""

from __future__ import annotations

import argparse
import json
import os

from harness_schema import MODEL_ROUTING_POLICY
from runtime_profiles import (
    SUPPORTED_MODEL_RUNTIMES,
    model_profiles_for,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select a progress-bounded model profile.")
    parser.add_argument(
        "--runtime",
        default="codex",
        help="Runtime mapping to resolve (codex|grok). Default: codex.",
    )
    parser.add_argument(
        "--routing-policy",
        default=MODEL_ROUTING_POLICY,
        help="Sealed routing policy to read (defaults to the current policy).",
    )
    parser.add_argument("--simple", action="store_true")
    parser.add_argument("--mechanically-verifiable", action="store_true")
    parser.add_argument(
        "--implementation",
        action="store_true",
        help="Explicitly delegate ordinary or heavy implementation to one bounded worker.",
    )
    parser.add_argument(
        "--micro-implementation",
        action="store_true",
        help=(
            "Route a confirmed micro implementation directly to parent/main; also pass "
            "all --micro-* confirmation flags."
        ),
    )
    parser.add_argument(
        "--micro-scope-local",
        "--scope-local",
        dest="micro_scope_local",
        action="store_true",
        help="Confirm that the micro change is local to one scope/module.",
    )
    parser.add_argument(
        "--micro-low-risk",
        "--low-risk",
        dest="micro_low_risk",
        action="store_true",
        help="Confirm that the micro change is low risk.",
    )
    parser.add_argument(
        "--micro-no-protected-boundary",
        "--no-protected-boundary",
        dest="micro_no_protected_boundary",
        action="store_true",
        help="Confirm that no protected/public-contract/migration boundary is involved.",
    )
    parser.add_argument(
        "--micro-context-complete",
        "--context-complete",
        dest="micro_context_complete",
        action="store_true",
        help="Confirm that the parent has complete implementation context.",
    )
    parser.add_argument(
        "--micro-short-verification",
        "--short-verification",
        "--micro-short-verification-cycle",
        dest="micro_short_verification",
        action="store_true",
        help="Confirm that one short verification cycle can prove the change.",
    )
    parser.add_argument(
        "--micro-delegation-cost-higher",
        "--delegation-cost-higher",
        dest="micro_delegation_cost_higher",
        action="store_true",
        help="Confirm that delegation costs more than direct parent execution.",
    )
    parser.add_argument("--fuzzy", action="store_true")
    parser.add_argument("--harness-synthesis", action="store_true")
    parser.add_argument("--high-risk", action="store_true")
    parser.add_argument("--protected-boundary", action="store_true")
    parser.add_argument("--public-contract", action="store_true")
    parser.add_argument("--migration", action="store_true")
    parser.add_argument("--worker-conflict", action="store_true")
    parser.add_argument("--validation-failures", type=int, default=0)
    parser.add_argument("--no-progress-cycles", type=int, default=0)
    parser.add_argument(
        "--new-diagnosis",
        action="store_true",
        help="Confirm that a stalled path has a new, bounded diagnosis before rerouting.",
    )
    parser.add_argument(
        "--allow-env-override",
        action="store_true",
        help="Apply HARNESS_<RUNTIME>_<PROFILE>_MODEL env overrides to the sealed map.",
    )
    return parser.parse_args()


MICRO_CONFIRMATIONS = (
    ("scope-local", "micro_scope_local", "scope_local"),
    ("low-risk", "micro_low_risk", "low_risk"),
    ("no-protected-boundary", "micro_no_protected_boundary", "no_protected_boundary"),
    ("context-complete", "micro_context_complete", "context_complete"),
    ("short-verification", "micro_short_verification", "short_verification"),
    ("delegation-cost-higher", "micro_delegation_cost_higher", "delegation_cost_higher"),
)


def _micro_confirmation_missing(args: argparse.Namespace) -> list[str]:
    missing: list[str] = []
    for label, primary, alias in MICRO_CONFIRMATIONS:
        if not bool(getattr(args, primary, False) or getattr(args, alias, False)):
            missing.append(label)
    return missing


def select_profile(
    args: argparse.Namespace,
    *,
    routing_policy: str | None = None,
) -> tuple[str, list[str]]:
    if args.validation_failures < 0:
        raise ValueError("validation failures must be non-negative")
    if args.no_progress_cycles < 0:
        raise ValueError("no-progress cycles must be non-negative")
    implementation = bool(getattr(args, "implementation", False))
    micro_implementation = bool(getattr(args, "micro_implementation", False))
    selected_policy = routing_policy or getattr(args, "routing_policy", MODEL_ROUTING_POLICY)
    micro_confirmations = any(
        bool(getattr(args, primary, False) or getattr(args, alias, False))
        for _, primary, alias in MICRO_CONFIRMATIONS
    )
    public_contract = bool(getattr(args, "public_contract", False))
    migration = bool(getattr(args, "migration", False))
    protected_boundary = bool(
        getattr(args, "protected_boundary", False) or public_contract or migration
    )
    if micro_implementation and selected_policy != MODEL_ROUTING_POLICY:
        raise ValueError(
            "--micro-implementation requires the current routing policy "
            f"{MODEL_ROUTING_POLICY!r}; sealed historical policies do not define this route"
        )
    if micro_confirmations and not micro_implementation:
        raise ValueError(
            "micro confirmation flags require --micro-implementation; "
            "they are not standalone routing signals"
        )
    if implementation and micro_implementation:
        raise ValueError(
            "--implementation and --micro-implementation are mutually exclusive; "
            "choose the explicit worker or parent-direct route"
        )
    if (implementation or micro_implementation) and (
        args.fuzzy
        or args.harness_synthesis
        or args.high_risk
        or args.worker_conflict
        or protected_boundary
        or args.validation_failures
        or args.no_progress_cycles
    ):
        raise ValueError(
            "implementation routing cannot combine with diagnosis/review/stall flags; "
            "route the decision first, then dispatch implementation separately"
        )
    if micro_implementation and (args.simple or args.mechanically_verifiable):
        raise ValueError(
            "--micro-implementation cannot combine with --simple or "
            "--mechanically-verifiable; mechanical batch routing is separate"
        )
    if micro_implementation:
        missing = _micro_confirmation_missing(args)
        if missing:
            raise ValueError(
                "--micro-implementation requires explicit confirmations: "
                + ", ".join(missing)
            )
    if args.validation_failures >= 2 or args.no_progress_cycles >= 2:
        if not args.new_diagnosis:
            raise ValueError("stalled execution requires a new diagnosis before routing")
        return "planner", ["fresh_diagnosis_after_stall"]
    if args.high_risk or args.worker_conflict or protected_boundary:
        reasons = []
        if args.high_risk:
            reasons.append("high_risk")
        if args.worker_conflict:
            reasons.append("worker_conflict")
        if protected_boundary:
            reasons.append("protected_boundary")
        return "critical_reviewer", reasons
    if args.fuzzy or args.harness_synthesis:
        return "planner", ["fuzzy_goal" if args.fuzzy else "harness_synthesis"]
    if micro_implementation:
        return "main", ["micro_implementation_direct"]
    if implementation:
        return "fast", ["implementation_worker"]
    if args.simple and args.mechanically_verifiable:
        return "fast", ["simple", "mechanically_verifiable"]
    return "main", ["default_high_frequency_main"]


def env_override_key(runtime: str, profile: str) -> str:
    return f"HARNESS_{runtime.upper()}_{profile.upper()}_MODEL"


def apply_env_overrides(
    runtime: str, profiles: dict[str, dict[str, str]]
) -> tuple[dict[str, dict[str, str]], list[str]]:
    applied: list[str] = []
    updated = {name: dict(config) for name, config in profiles.items()}
    for profile, config in updated.items():
        key = env_override_key(runtime, profile)
        value = os.environ.get(key, "").strip()
        if value:
            config["model"] = value
            applied.append(key)
    return updated, applied


def resolve_configuration(
    runtime: str,
    profile: str,
    *,
    routing_policy: str = MODEL_ROUTING_POLICY,
    allow_env_override: bool = False,
) -> tuple[dict[str, str], list[str]]:
    runtime_key = (runtime or "").strip().casefold()
    if runtime_key not in SUPPORTED_MODEL_RUNTIMES:
        supported = ", ".join(sorted(SUPPORTED_MODEL_RUNTIMES))
        raise ValueError(f"unsupported runtime {runtime!r}; expected one of: {supported}")
    profiles = model_profiles_for(runtime_key, routing_policy)
    if profiles is None or profile not in profiles:
        raise ValueError(f"no sealed profile {profile!r} for runtime {runtime_key!r}")
    overrides: list[str] = []
    if allow_env_override:
        profiles, overrides = apply_env_overrides(runtime_key, profiles)
    return dict(profiles[profile]), overrides


def main() -> int:
    args = parse_args()
    try:
        profile, reasons = select_profile(args, routing_policy=args.routing_policy)
        configuration, overrides = resolve_configuration(
            args.runtime,
            profile,
            routing_policy=args.routing_policy,
            allow_env_override=args.allow_env_override,
        )
    except ValueError as exc:
        print(f"ERROR {exc}")
        return 2
    payload = {
        "policy": args.routing_policy,
        "runtime": args.runtime.strip().casefold(),
        "profile": profile,
        "model": configuration["model"],
        "reasoning_effort": configuration["reasoning_effort"],
        "reason_codes": reasons,
        "env_overrides_applied": overrides,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
