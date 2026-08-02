# Stop Conditions

Stop and ask for a decision, narrow the scope, or create a new stage when any condition applies.

## Hard Stops

- The task now requires deleting data, publishing, deployment, permission changes, production data access, paid API usage, or irreversible operations.
- The user's stated goals conflict, or acceptance criteria cannot be inferred safely.
- A required dependency, credential, environment, or external service is unavailable.
- The agent is about to revert or overwrite changes it did not make.
- Verification has failed twice for the same stage without a new diagnosis.
- Two consecutive cycles produced no new evidence, artifact change, test result, or binding
  decision.

## Multi-Agent Stops

- File ownership overlaps between agents and no merge plan exists.
- A sub-agent reports assumptions that contradict the manager's spec or another sub-agent's report.
- Previous worktrees, reports, or temporary resources are still running or contain unmerged work.
- The manager cannot verify a sub-agent's output from its report and evidence.

## Scope Stops

- The implementation requires a larger architecture change than the spec allowed.
- A "small fix" has become a cross-module migration, data model change, or user-facing behavior change.
- More than one viable design remains and the choice affects future product or maintenance direction.

## Quality Stops

- The result depends on stubs, TODOs, mocked data, or placeholder behavior that would be mistaken for real completion.
- Web/UI work has not been checked in a browser when browser verification is available.
- The final answer would need to claim success without tests, logs, screenshots, readback, or another concrete evidence source.

## Budget Stops

- The current stage is consuming too much context, time, tool calls, or external cost relative to the spec.
- Continuing would make the task harder to resume because state has not been written down.

## Stall Stop Packet

For a reasoning stall, record facts, assumptions, the current hypothesis, the falsifying
experiment already attempted, and whether any new evidence appeared. Do not increase effort
or repeat the same route. Use one fresh bounded diagnosis only when the packet identifies a
genuinely different question.

When stopping, leave a concise handoff: current state, evidence, blocker, options,
recommendation, and the exact decision needed.
