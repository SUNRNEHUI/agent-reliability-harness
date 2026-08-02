# Claude Code Runtime Adapter

Use Claude Code's native planning/task facilities for Native work. Do not create harness
state while the active session can finish and verify safely.

Materialize Portable state before a session/provider switch, long wait, or multi-worker
boundary. The replacement agent must be able to continue from the workspace and capsule
without Claude-specific memory, transcript, or task IDs.

## Capabilities

Verify file access, shell, hooks, subagents, worktree safety, browser or MCP tools, and
whether model selection is actually exposed. Record only capability gaps that affect the
contract.

Use native subagents for disjoint responsibilities. If unavailable, execute the same
bounded work sequentially and record that fallback. Never let two workers mutate shared
state without an explicit merge owner.

## Portable Resume

```bash
python3 <skill-dir>/scripts/harnessctl.py resume <project-root> \
  --runtime claude --actor-id <session-id>
```

Read the returned capsule first, reconcile workspace drift, and use the current epoch for
later checkpoint or handoff commands. Provider-local history is optional context, not
acceptance evidence.

## Verification

Follow repository instructions and hooks, but re-check the critical test, diff, or artifact
before PASS. Escalate to Audited extensions for high-risk state, protected evidence,
destructive actions, or production-visible behavior.
