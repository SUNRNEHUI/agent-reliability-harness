# Forward routing eval

`forward_cases.json` contains eight small, user-facing prompts and the routing
decision expected from an agent. The dimensions are:

- `mode`: `native`, `portable`, or `audited`;
- `load_coding_workflow`: whether the repository coding workflow is loaded;
- `delegation`: `none`, bounded worker delegation (`bounded`), or deferred
  delegation pending approval (`deferred`);
- `durable_artifacts`: whether durable harness state is expected;
- `approval`: whether approval is required before the requested action.

An agent should write one structured result per case, for example:

```json
{
  "results": [
    {
      "case_id": "native_typo",
      "mode": "native",
      "load_coding_workflow": false,
      "delegation": "none",
      "durable_artifacts": false,
      "approval": "not_required"
    }
  ]
}
```

Score the output with:

```bash
python3 tests/evals/score_forward.py \
  --cases tests/evals/forward_cases.json \
  --results /path/to/agent-results.json
```

The scorer compares only the structured fields. It does not search prompts,
notes, or other prose for keywords, and a PASS means only that the declared
routing fields match this fixture—not that the agent completed the task.
