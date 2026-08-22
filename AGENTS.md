# AGENTS.md

本文件是 `agent-reliability-harness` 项目的项目级规则。它覆盖用户级通用规则中与本项目冲突的部分。

## 项目定位

本仓库维护一个运行时中立、Plan-native 的可靠性 skill。它复用 Codex、Claude Code、Grok 等运行时的原生规划，只在任务需要跨会话、跨模型或强审计时增加持久状态。

核心原则：

- 默认选择能可靠完成任务的最轻模式：Native、Portable、Audited。
- Native 使用运行时原生 Plan，不写 harness 文件，也不复制计划。
- Portable 只保存 `contract.json`、`events.jsonl`、`capsule.md`；`contract.json` 是唯一可变真相。
- Audited 才启用 typed receipts、Production State Witness、受保护 TDD chronology、evaluator 和更强 fencing。
- 并行是执行选择，不是模式；只有责任边界独立且收益高于协调成本时才使用 worker。
- Portable 核心只保存可观察事实，不保存 chain-of-thought、完整聊天、provider reasoning、secret 或 in-flight 外部副作用。
- 保持 legacy `handoff-v1` Full artifact 可恢复，不静默迁移或破坏旧格式。
- provider/model slug 只能存在于 runtime profile 或 adapter，不进入 Portable contract。

## 主要文件

- `skills/agent-reliability-harness/`：唯一、完整、可直接安装的 runtime Skill 包。
- `skills/agent-reliability-harness/SKILL.md`：Skill 入口协议和触发说明。
- `skills/agent-reliability-harness/VERSION`：当前发布版本的单一来源。
- `README.md` / `README.zh-CN.md`：公开说明，必须保持英文和中文同步。
- `skills/agent-reliability-harness/references/`：运行时按需加载的协议材料。
- `skills/agent-reliability-harness/templates/`：运行时需要的 artifact 与 worker 模板。
- `skills/agent-reliability-harness/scripts/`：控制器、validator、status、TDD 和 witness 运行时脚本。
- `tests/`：行为、拒绝边界和开放包结构契约测试；不得放进 runtime Skill 包。
- `scripts/package_skill.py`：校验、复制并比较权威 `skills/` 包，不维护第二份文件白名单。
- `scripts/sync_version.py`：从 Skill 包内的 `VERSION` 同步公开版本引用。
- `docs/legacy/`：不进入 runtime 的历史 prompt、旧协议说明和开发工具。

## 修改规则

- 修改 skill 行为时，优先改行为测试，再改 Skill 包内的 `SKILL.md`、`references/`、模板和脚本。
- 修改公开行为或版本时，必须同步 `README.md` 和 `README.zh-CN.md`。
- 修改当前版本时，先改 Skill 包内的 `VERSION`，再运行 `python3 scripts/sync_version.py --fix --date YYYY-MM-DD`。
- `skills/agent-reliability-harness/` 目录本身就是 runtime 权威边界；新增 runtime 文件不需要再登记白名单。
- repository-only 测试、fixture、历史文档和维护工具不得进入 Skill 包。
- 不要把 `workspace/`、`.harness/`、缓存、session 日志、私有配置或生成 artifact 加入 runtime 包。
- 不要把本地安装目录 `~/.codex/skills/agent-reliability-harness` 当成源码。源码以本仓库为准。
- `README.md` 与 `README.zh-CN.md` 的标题结构必须一致。
- Skill 包内的 `SKILL.md` 默认不超过 750 words，`agents/openai.yaml` 不超过 120 words。
- 保持 diff 小而聚焦，不做无关重排、格式化或重命名。

## TDD 和验证

改动脚本或模板结构时，优先使用最小可行 Testing Gate：

1. 先明确要拒绝或接受的结构。
2. 能写负例时，先用现有 validator 或临时 fixture 证明当前缺口。
3. 再修改脚本或模板。
4. 最后运行相关验证命令。

修改触发、模式、delegation 或持久化路由时，还必须更新
`tests/evals/forward_cases.json`。让一个看不到 `expected` 的独立 Agent 对原始 prompt
输出结构化结果，再用 `tests/evals/score_forward.py` 评分；静态关键词断言不能替代该评测。

常用验证命令：

```bash
python3 -m unittest discover -s tests -v
python3 tests/test_runtime_behavior.py
python3 tests/protocol_regression_harness.py \
  --skill-root skills/agent-reliability-harness --pretty
python3 -m py_compile scripts/*.py skills/agent-reliability-harness/scripts/*.py tests/*.py
python3 scripts/package_skill.py --verify-source
python3 scripts/package_skill.py --output /tmp/agent-reliability-harness-runtime --force
python3 scripts/package_skill.py --check /tmp/agent-reliability-harness-runtime
python3 -m json.tool skills/agent-reliability-harness/templates/worker_result.json >/dev/null
git diff --check
```

如果改动影响 TDD trace：

```bash
python3 skills/agent-reliability-harness/scripts/tdd_gate_check.py \
  docs/legacy/templates/tdd_trace.jsonl
```

如果同步本地安装，必须先生成干净 runtime 包：

```bash
rsync -a --delete --exclude workspace --exclude .harness \
  /tmp/agent-reliability-harness-runtime/ /Users/sunrenhui/.codex/skills/agent-reliability-harness/
python3 scripts/package_skill.py --check /Users/sunrenhui/.codex/skills/agent-reliability-harness
```

## 发布规则

发布前必须确认：

- Skill 包内的 `VERSION`、`SKILL.md` 与中英文 README 当前版本一致。
- release history 中英同步。
- runtime 包能干净生成。
- 本地安装目录与 runtime 包一致。
- `git status` 中没有意外文件。

GitHub 发布通常包含：

- commit
- tag，例如 `vX.Y.Z`
- push main
- push tag
- GitHub release notes
- runtime zip，如需要

## 多 agent 使用

本项目可以使用多 agent 辅助开发，但主 agent 必须保留最终责任：

- 子 agent 适合做只读审查、独立实现、对抗式评估、文档一致性检查。
- 修改同一文件前要明确 owner，避免并行冲突。
- reviewer/evaluator 默认应在实现任务之后运行，不应和被审查实现并行，除非它只审查已存在 artifact。
- 主 agent 合并结果后必须亲自 review diff 和运行验证。
