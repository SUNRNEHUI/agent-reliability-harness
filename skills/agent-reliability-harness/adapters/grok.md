# Grok Runtime Adapter

Use Grok's native planning and execution for Native work. The density decision comes before
delegation or model routing: do not create workers or artifacts for a task the active
session can finish and verify directly.

## Portable Continuation

Materialize a Portable Contract before crossing a Grok/Codex/Claude boundary. Resume from
the project root:

```bash
python3 <skill-dir>/scripts/harnessctl.py resume <project-root> \
  --runtime grok --actor-id <session-id>
```

The capsule, workspace fingerprint, evidence index, and next action are authoritative.
Grok-local chat state and provider reasoning are not portable requirements.

## Workers And Fallback

Use real parallel workers only when the active Grok surface exposes them and ownership is
disjoint. Otherwise run bounded stages sequentially and report the fallback. Never describe
sequential execution as parallel.

## Optional Legacy Model Profiles

The existing compatibility map assumes the configured Grok 4.5 endpoint is `grok-api` for
every profile, with reasoning effort differentiating fast, main, planner, and critical
review. A cheaper second model remains opt-in. Keep these slugs in this adapter and
`references/model-routing.md`, never in a Portable Contract.

Runtime routing is optional and follows mode selection. Record requested and resolved model
separately when the surface exposes the latter; a requested slug is not execution evidence.

## Verification

Follow project instructions, inspect the final diff, and rerun the critical check. Missing
shell, browser, or permissions narrows acceptance or blocks it. Use Audited extensions only
when risk requires typed evidence, state witness review, fencing, or stronger rollback.
