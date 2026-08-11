# Agent Reliability Harness

简体中文 | [English](README.md)

Agent Reliability Harness 是一个面向 Codex、Claude Code、Grok 及其他具备文件与
shell 能力代理的 Plan-native 可靠性 skill。普通任务直接复用运行时原生 Plan；只有
任务必须跨越边界时才物化紧凑、provider-neutral 的合同；只有风险需要时才增加审计控制。

当前版本：**v9.2.0** · 2026-08-11

---

## 概览

现代 agent 已经具备规划、任务跟踪、工具调用和 worker 管理能力。再在 prompt 中实现
第二套状态机会浪费上下文，并制造相互竞争的真相源。本 skill 只补充运行时无法可靠
带过会话或模型边界的部分。

主代理始终负责：

- 选择 Native、Portable 或 Audited
- 定义结果、约束、授权边界和可观察的 `done_when`
- 只物化昂贵或不安全的重建信息
- 只在责任边界独立时分配 worker
- 停止没有产生可观察进展的推理循环
- 在声明完成前验证验收证据

子代理只负责边界明确的执行、调研、审查或评估任务。最终验收责任仍由主代理承担。

---

## 核心能力

- **Plan-native 路由：** 复用运行时 Plan，不再生成第二份 checklist。
- **Portable Contract v2：** 只保存目标、决策、里程碑、阻塞、下一动作、workspace
  fingerprint、证据摘要、能力和分级读取路径。
- **有界 resume 上下文：** 在确定性的字符预算内重新生成 `capsule.md`。
- **Fail-closed 续接：** 写入前检测损坏、drift、过期 owner、多个 active run 和跨协议歧义。
- **Audited 扩展：** 高风险任务保留 typed receipts、Production State Witness、受保护
  TDD chronology、evaluator separation 和更强 fencing。
- **旧格式兼容：** 继续校验和恢复 `handoff-v1` Full artifact。
- **Adapter-local 路由：** provider 和 model slug 不进入 Portable 核心；只有派发收益
  明确时才使用已配置的 `luna_worker` 执行有界任务。
- **进度熔断：** 每轮必须产生推进明确验收边界的新证据、artifact 变更、测试结果或
  约束性决策；连续两轮无进展且没有新诊断时停止。
- **精简打包：** 排除重复 prompt、仓库测试/eval、生成的 `.harness/` / `workspace/`
  artifact、缓存、session 和私有配置。

---

## 执行模式

| 模式 | 适用场景 | 持久状态 |
| --- | --- | --- |
| **Native** | 当前 session 可以完成并验证，丢失上下文不会造成昂贵重建。 | 无；使用运行时 Plan 和任务跟踪。 |
| **Portable** | 工作可能跨 session/model、等待外部状态，或 worker 结果必须跨 context loss 保留。 | `.harness/<slug>/contract.json`、`events.jsonl`、`capsule.md` |
| **Audited** | 生产、发布、权限、安全、破坏性变更、owner 争议或高假完成风险需要更强证据。 | Portable 状态加按风险启用的证据与审查扩展；兼容 legacy Full。 |

并行与模式相互独立。大型顺序任务可以保持 Native；小型交接可以是 Portable；
一个文件的高风险变更也可以是 Audited。

---

## 适用场景

当请求涉及以下能力时使用本 skill：

- 输入“你是主 agent”或“写一个 harness”以启动一次模式判断
- “写一个 harness 来解决这个问题”
- 持久 handoff 或跨模型续接
- 可续跑执行或长时间外部等待
- 多智能体、sub-agent、并行、DAG 或 worktree 协同
- 分头处理 / 分别派 / 拆给不同 agent
- 证据化验收或高假完成风险

触发 skill 不等于选择 worker 或最重模式。仓库现有流程足够时，普通实现、规划和测试
保持 Native。只有 worker 的有界责任能带来大于协调成本的收益时才派发。

---

## 运行流程

```text
Native Plan
-> 定义 outcome / constraints / done_when / approval boundary
-> 选择 Native / Portable / Audited
-> 执行；必要时使用有界 worker
-> 连续两轮无进展时停止或重新诊断
-> 用可观察证据验证
-> 只在持久边界 checkpoint 或 handoff
```

主代理应选择能够保证安全执行和真实完成的最轻模式。不要把原生 Plan 再复制到 JSON
或 Markdown。

只有用户要求持久目标，或停止条件还无法度量时，才使用 `define-goal` 或可用的持久目标
工具。定义 goal 本身不会授权 Portable 状态、Audited 控制或 worker。

## 进度与 Codex 路由

进展只包括能推进明确 `done_when` 或关键路径 blocker 的新证据、artifact 变更、测试
结果或约束性决策。生成报告、重建 package、扩大清单和辅助检查不推进该验收边界时不算
进展。连续两轮无进展后只运行一个证伪实验；仍没有新证据就停止该推理链。

当 Codex 支持显式路由时，父 Agent 按其已配置的 Sol effort 负责规划和验收。本机已安装
的 `luna_worker` 可以用 Luna `max` 执行确有派发价值的长任务、机械任务或独立可验证任务。
自定义 Agent 调用使用自包含的 `fork_turns=none` 任务。说“你是主 agent”不会自动启动
它；只有具体候选结果出现后才审查，只有新诊断或新证据出现后才重试。requested model
和 resolved model 分开记录。

---

## Portable 与 Audited 协议

Portable v2 是默认持久协议。Audited 控制是扩展，不是每次都必须执行的第二套工作流。

### 1. 物化合同

只有原生 Plan 已经可执行且存在持久化触发条件时，才物化合同：

```bash
python3 <skill-dir>/scripts/harnessctl.py materialize . \
  --title "Checkout refactor" \
  --goal "完成 checkout 重构且不改变公开行为" \
  --done-when "focused 与 regression 测试通过" \
  --constraint "保留无关改动" \
  --next-action "检查 checkout 状态边界"
```

命令只在 `.harness/<slug>/` 下创建三个核心文件：

- `contract.json`：唯一可变真相
- `events.jsonl`：append-only transition 与 evidence 索引
- `capsule.md`：为接收模型重新生成的有界上下文

### 2. 在已验证边界 Checkpoint

只在有意义的验证结果之后或可能中断之前 checkpoint，不要每次 tool call 后都写入。
证据留在项目中；合同只保存相对路径、SHA-256 和文件大小。

```bash
python3 <skill-dir>/scripts/harnessctl.py checkpoint . \
  --runtime codex --actor-id codex-main --owner-epoch 1 \
  --completed "Focused regression passes" \
  --next-action "Run the package verification" \
  --evidence-file reports/focused-test.txt \
  --reason "Verified implementation boundary"
```

第一次 checkpoint 会领取 epoch 1，因此省略 `--owner-epoch`。

### 3. Handoff 与 Resume

正常交接使用 `handoff`。替代运行时从项目根开始：

```bash
python3 <skill-dir>/scripts/harnessctl.py resume . \
  --runtime claude --actor-id claude-main
```

`resume` 会校验合同、拒绝同时 active 的 Portable/Full 歧义、检查 workspace drift、转移
owner、重建 capsule，并返回 `must_read`、`read_if_needed`、blockers、pending
verification 和一个安全 next action。强制接管 active owner 时还必须提供
`--takeover-reason`。

到达终态时运行 `close --status accepted|failed|cancelled`。`accepted` 要求已有证据且
没有 unresolved blocker 或 pending verification；关闭后的合同不再参与 active run 选择。

### 4. Portable 数据边界

只持久化可观察事实：目标、`done_when`、约束、已完成里程碑、阻塞、带简短理由的决策、
changed paths、证据摘要、能力和分级读取路径。不要持久化隐藏 reasoning、完整聊天、
provider session object、secret 或 in-flight 外部副作用。

### 5. Audited 升级

只增加风险真正需要的控制：

- typed acceptance receipts 与 manager re-verification
- UI/state/async/concurrency 路径的 Production State Witness
- 行为变更的受保护 RED/GREEN chronology
- evaluator separation、更强 rollback 和详细 trace
- owner 争议或并发 writer 的 epoch fencing

Audited 不等于必须并行。worker 仍是独立的成本与责任边界决策。

### 6. Legacy Full 兼容

`workspace/<slug>/` 下的既有 `handoff-v1` artifact 继续有效。同一组 `checkpoint`、
`handoff`、`resume` 和 `validate` 命令仍支持它们。不要仅为换格式重写有效旧 artifact。

### 7. 验收边界

worker self-report 和 harness score 都不是完成证据。manager 必须重新运行或检查关键
验证。对用户可见故障，在 flow 或 visible evidence 可用时，policy-only unit test 不能
替代它们。

---

## 安装

克隆仓库：

```bash
git clone https://github.com/SUNRNEHUI/agent-reliability-harness.git
cd agent-reliability-harness
```

生成干净的 runtime 包：

```bash
python3 scripts/sync_version.py
python3 scripts/package_skill.py --verify-source
python3 scripts/package_skill.py --output /tmp/agent-reliability-harness-runtime --force
```

安装到 Codex：

```bash
mkdir -p ~/.codex/skills/agent-reliability-harness
rsync -a --delete --exclude workspace --exclude .harness \
  /tmp/agent-reliability-harness-runtime/ ~/.codex/skills/agent-reliability-harness/
python3 scripts/package_skill.py --check ~/.codex/skills/agent-reliability-harness
```

runtime 包只包含 skill 运行时需要的文件。

这套路由策略推荐使用以下 Codex 默认配置：

```toml
model = "gpt-5.6-sol"
model_reasoning_effort = "max"
service_tier = "fast"

[agents]
default_subagent_model = "gpt-5.6-luna"
default_subagent_reasoning_effort = "max"
```

这段配置是可选的，始终由用户自行维护。Skill 安装过程不复制私有 model cache，也不
设置 `model_catalog_json`。如果 Luna 不可用，应保留 requested route，并单独记录运行时
实际解析的 fallback；不能声称 Luna worker 已经运行。

可选的命名 worker 可以把有界执行通道显式化：

```toml
# ~/.codex/agents/luna-worker.toml
name = "luna_worker"
description = "处理边界清晰任务"
model = "gpt-5.6-luna"
model_reasoning_effort = "max"
developer_instructions = "只执行明确委派任务，返回简洁证据结果，不扩大范围。"
```

Skill 不会创建这个个人配置文件。Codex 已安装并识别它时，adapter 使用
`fork_turns=none` 并发送自包含任务；缺少它时正常 fallback，不把缺少命名 Agent 当作
任务失败。

---

## 从旧名称迁移

早期版本曾使用 Agent Dispatch Harness 作为公开项目和 runtime 名称，更早版本使用 `multi-agent-dispatcher`，一些本地安装也使用过 `multi-agent-orchestrator`。新的安装和公开传播应统一使用 `agent-reliability-harness`。

升级已有本地安装时，先安装新的 runtime 目录；如果旧目录仍存在且不再需要，可以删除：

```bash
rm -rf ~/.codex/skills/agent-dispatch-harness ~/.codex/skills/multi-agent-dispatcher ~/.codex/skills/multi-agent-orchestrator
```

这样可以避免同一套工作流以多个 skill 名称重复出现。

---

## Runtime 包内容

runtime 包包含：

- `VERSION`
- `SKILL.md`
- `agents/openai.yaml`
- `adapters/`
- `SKILL.md` 或 Audited 协议直接加载的 references
- controller、validator、status、模型路由、TDD 和 State Witness scripts
- 只有 runtime 命令实际复制或 worker contract 需要的 templates

权威文件清单以 `scripts/package_skill.py:RUNTIME_FILES` 为准；本节只概括 runtime 类别。

runtime 包会排除：

- `README.md`
- `README.zh-CN.md`
- `scripts/sync_version.py`
- `scripts/package_skill.py`
- 重复的 `master-prompt.md` 和 `sub-prompt.md`
- 仓库回归测试、协议 eval case 和 skill 自评分工具
- 没有 runtime consumer 的 source-only references 与 templates
- `.git`
- 生成的 `.harness/` artifact
- 生成的 workspace artifact
- 本地 memory 文件
- session 日志
- 缓存和字节码
- 私有配置
- 凭据或 API key

---

## 使用示例

明确的多智能体请求：

```text
这个项目有前端、后端和测试三块。请在有价值的地方使用多个 agent，并提供验证证据。
```

带有多智能体措辞的小任务：

```text
如果需要可以用多智能体，帮我修正这个错别字。
```

预期行为：保持 Native，不进行调度，因为协调开销没有必要。

需要持久化协同的长任务：

```text
重构 checkout，更新 API contract，迁移测试，并验证 UI 流程。请使用子 agent，并让任务可以续跑。
```

预期行为：因为任务必须续跑，所以物化 Portable 状态；只有实际风险需要时才增加
Audited 扩展。是否使用 worker 仍是独立决策。

---

## Portable 物化与 Audited 初始化

新的可续跑任务使用 Portable v2：

```bash
python3 scripts/harnessctl.py materialize /path/to/project \
  --title "Checkout Refactor" \
  --goal "重构 checkout 并保留现有行为" \
  --done-when "Checkout regression suite passes" \
  --next-action "Inspect the production checkout flow"
```

只生成：

```text
/path/to/project/.harness/checkout-refactor/
├── contract.json
├── events.jsonl
└── capsule.md
```

新建 Audited run 时，初始化受保护记录：

```bash
python3 scripts/init_run.py \
  --project-root /path/to/project \
  --mode audited \
  --title "Checkout Refactor" \
  --agents frontend,backend,tests
```

生成目录示例：

```text
/path/to/project/workspace/checkout-refactor/
├── acceptance_registry.json
├── capability_snapshot.md
├── task_spec.md
├── progress.md
├── run_state.json
├── trace.jsonl
├── tdd_trace.jsonl
├── evaluator_report.md
└── tasks/
    ├── 1.1-frontend.md
    ├── 1.2-backend.md
    └── 1.3-tests.md
```

生成的 `run_state.json` 写入 `mode: audited`。既有 `mode: full` `handoff-v1`
artifact 仍可读取和恢复，但新示例与默认值不再创建该 legacy mode。

---

## 报告校验

直接校验 Portable contract：

```bash
python3 scripts/harnessctl.py validate /path/to/project/.harness/checkout-refactor
```

对于 Audited 或 legacy artifact，在使用报告结论前先校验报告结构：

```bash
python3 scripts/validate_report.py <artifact-dir>/1.1-frontend-report.md --type subagent
```

支持的 artifact 类型：

- `spec`
- `progress`
- `subagent`
- `evaluator`

如果 `acceptance_registry.json` 或 `run_state.json` 与被校验 artifact 位于同一目录，校验器也会检查这些协议文件。

对于 TDD 敏感任务，可以校验专用 TDD trace：

```bash
python3 scripts/tdd_gate_check.py <artifact-dir>/tdd_trace.jsonl
```

该 checker 会校验 strict TDD 的时间顺序，接受已记录的 test-first gap evidence，并拒绝缺少替代验证理由的 substitute gate。

在可用时，建议通过测试包装器运行验证命令，让 trace 事件由运行时命令包装器生成，而不是由 agent 手写：

```bash
python3 scripts/harness_test_run.py \
  --trace <artifact-dir>/tdd_trace.jsonl \
  --task-id 1.1 \
  --gate-mode strict_tdd \
  --phase RED \
  --run-state <artifact-dir>/run_state.json \
  -- pytest path/to/test.py
```

对于 strict TDD 循环，可以使用 `tdd_gate_check.py --source-path <file>` 为当前循环改动的源文件增加文件系统 mtime 校验。

对于 CI 或发布 gate，可以要求 run 达到 high completion confidence：

```bash
python3 scripts/status.py <artifact-dir>/run_state.json --require-high-confidence
```

---

## 仓库结构

```text
agent-reliability-harness/
├── SKILL.md
├── README.md
├── README.zh-CN.md
├── adapters/
├── agents/
├── references/
├── scripts/
├── templates/
├── master-prompt.md
└── sub-prompt.md
```

详细协议材料位于 `references/`，运行时适配说明位于 `adapters/`。

---

## 运行时适配

协议本身不绑定特定运行时。适配文档说明如何在不同代理环境中落地：

- [Codex adapter](adapters/codex.md)
- [Grok adapter](adapters/grok.md)
- [Claude Code adapter](adapters/claude-code.md)
- [Portable Contract v2](references/portable-contract.md)
- [Audited 与 legacy 协议](references/harness-protocol.md)

适配文档把原生 planning、worker 控制和可选模型 profile 映射到不同运行时，但不能把
provider-specific 字段加入 Portable contract。

---

## 与 Superpowers 的关系

本项目是独立实现，不依赖 Superpowers 运行。

本项目在设计上参考了 [obra/superpowers](https://github.com/obra/superpowers) 中的部分工程实践。Superpowers 是 Jesse Vincent 创建的软件开发方法体系。Agent Reliability Harness 借鉴的方向包括 test-first evidence、fresh-context sub-agents、review gates、worktree isolation 和 verification before completion。

本项目不复制 Superpowers 的 skill 正文，也不要求安装 Superpowers 插件。二者关系如下：

```text
agent-reliability-harness = 持久化与验收权威
Superpowers-style methods = 可选的工程支持方法
```

Native / Portable / Audited 选择始终先执行。只有支持方法适合当前模式和实际风险时才使用。

---

## 版本历史

### v9.2.0

- 将 Native 做成真正的一次判断快速路径：不会仅因 skill 触发就加载 reference、创建
  artifact、路由模型或派发 worker。
- 新增条件式 `luna_worker` 路由，用自包含的 `fork_turns=none` 任务执行；父 Agent 仍
  负责规划与最终验收。
- 新 Audited artifact 写入 `mode: audited`，同时保留旧 `mode: full` 的校验、发现、
  TDD digest 保护、handoff 和 resume。
- 从 runtime 包移除重复 prompt、开发测试/eval、自评分工具和未被消费的 source template，
  但不删除仓库回归资产。
- 将进展绑定到明确验收边界，并为 Portable checkpoint 增加显式 capsule 预算。

### v9.1.0

- 将 Codex 规划和验收统一到 Sol `max`，同时继续把确有必要的执行路由给 Luna `max`。
- 记录可选的 Codex 父 Agent / 子 Agent 配置，并把私有 model cache 覆盖排除在分发包外。
- 明确 routed profile 不会替代活跃父线程，并要求分别记录 requested model 与 resolved model。

### v9.0.0

- 新增可观察的进度熔断：连续两轮无进展后停止，重新路由前必须提供新诊断。
- 将长时间和机械 Codex 执行路由到 Luna `max`；Sol 仅用于有界的诊断、规划和具体验收审查。
- 将新路由版本化为 `progress-bounded-v2`，同时保留旧 `cost-aware-v1` Audited run
  的封存校验能力。
- 从通用 skill 入口移除特效复原专用策略，并减少重复的计划、报告和审查说明。

### v8.0.0

- 用 Plan-native 的 Native、Portable、Audited 模式替换 prompt 层 Direct/Lite/Full router。
- 新增 Portable Contract v2：三文件核心、有界 resume capsule、分级读取、证据摘要、
  workspace drift 检查、跨运行时 owner 转移和 terminal close。
- 保持 `handoff-v1` Full 兼容，将 provider/model map 移出 portable schema，并只在
  Audited 工作中保留重型证据控制。

### v7.5.0

- 为 Full run 增加 typed evidence hardening、artifact binding、lessons integrity、
  protected TDD chronology 和对抗式协议回归覆盖。

### v7.4.0

- 新增唯一 active run 自动发现、事务恢复、跨运行时 owner 原子转移、完整 resume packet、显式 checkpoint/handoff 命令和旧 Full artifact 自动升级。
- 新增 actor+epoch fencing、歧义/损坏 fail-closed、工作树内容 drift 检测和 continuation 状态输出。
- 将既有 v7.3 Grok 模型路由和证据 refresh 命令带回源码，并对齐 Codex/Grok/universal adapter 与 runtime 包内容。

### v7.3.0

- 新增封装的 Grok 模型 profile、确定性的 `--runtime grok` 路由、Grok adapter 和可选低成本模型配置，不虚构本地不存在的默认模型。
- 新增 `task-refresh` 和 `acceptance-refresh`，用于按路径事务化替换过期 artifact receipt。

### v7.2.0

- 为 state/UI/async/concurrency 任务增加 Production State Witness 契约，要求记录真实 source locator、可达的 failing/fixed/preserved truth-table 行、Observed before/Expected after，以及独立审查入口。
- 将 witness 接入运行时门禁：stateful artifact 未通过 witness 校验时不能 seal、dispatch、validate 或进入 protected acceptance；独立 review 证据必须达到配置的 policy/flow/user-visible 层级。
- 新增 `witness-set`、sealed witness digest、sealed-baseline dispatch 检查、对抗式压力测试和 source/install package 漂移检查。

### v7.0.0

- 将项目和 runtime skill 正式更名为 Agent Reliability Harness。
- 围绕策略驱动、按比例执行和基于证据验收的定位，重写公开 README 并同步 runtime metadata。

### v5.11.0

- 对照 `Cjbuilds/Codex-Orchestration`，记录吸收的薄路由思路，以及明确取消或不引入的高开销 bridge 和 ceremony。
- 保持当前父任务模型为唯一 root orchestrator，让显式 `no subagents` 指令拥有最高优先级，并收紧真实模型路由状态的表达。
- 新增 `scripts/status.py --require-high-confidence`，供 CI 或发布 gate 使用；默认人读状态输出保持不变。
- 将默认对齐提问收敛到不可逆或影响验收的决策；普通歧义改为说明可回滚假设后继续执行。

### v5.10.0

- 新增面向 GPT-5.6 的 Codex 路由策略：在运行时支持显式控制时，简单子 agent 默认使用 Luna/low，中等任务升级 Terra，高风险审查使用 Sol。
- 新增 worker 数量、嵌套深度、task-local context、紧凑报告和模型覆盖不可用时的回退规则。
- 将 Superpowers 风格方法改为按风险触发的可选方法，不再默认套用整套 ceremony。
- 新增模型路由参考、回归用例和 runtime 打包覆盖，同时不引入 GPT-5.6 专属 API 字段。

### v5.9.0

- 新增按模式成比例执行的 Completion Confidence Loop，在最终交付前把完成声明映射到最新证据。
- 扩展 Verification 和 Evaluator 指导，要求暴露缺失检查、过期证据、stub、TODO、mock 和未验证关键路径。
- 增强 `scripts/status.py`，输出任务完成度、验收汇总、证据缺口、置信度档位和下一步验证建议。
- 在 progress ledger 和 Lite plan 模板中增加轻量的 confidence 与 evidence gap 提示。
- 保持执行模式按需收敛：Direct 仍不创建 artifact，Lite 仍保持紧凑，Full 仍用于高风险或可续跑任务的持久化协议。
- 未新增 artifact 类型。

### v5.8.0

- 新增 `VERSION` 和 `scripts/sync_version.py`，让当前版本引用可以从单一来源检查或更新。
- 为 runtime 包新增 `scripts/package_skill.py --verify-source` 和 `--check <install-dir>` 检查。
- 通过 `templates/lite_plan.md`、`templates/lite_review.md` 和 `init_run.py --mode lite` 增加 Lite Orchestration artifact。
- 保持 `progress.md` 轻量，并新增 `scripts/status.py` 从 `run_state.json` 生成单屏状态摘要。
- 为 `lite_plan`、`lite_review` 和 Lite `run_state.json` 增加 validator 支持，并新增 runtime 行为测试。
- 本版本不加入自动 mode-router evaluation；`references/eval_cases.md` 仍作为人读回归集合。

### v5.7.0

- 为 Full Harness run 新增明确的 State / Memory 边界。
- 明确 `task_spec.md` 是本地人读计划/spec，`run_state.json` 是机器可读实时状态。
- 新增 `state_layers`，区分 Working State、Session State、Execution Log 和 Memory Boundary。
- 新增 `references/state-memory-boundary.md`，并纳入 runtime 打包。
- 更新校验逻辑，要求 `run_state.json` 包含核心 `state_layers` 结构。

### v5.6.0

- 将公开项目和运行时 skill 从 Multi-Agent Dispatcher 重命名为 Agent Dispatch Harness。
- 更新仓库 URL、安装路径、runtime metadata 和中英文公开文档。
- 将 TDD 命令包装器重命名为 `scripts/harness_test_run.py`，并更新 trace `source` 字段。
- 增加旧本地安装名 `multi-agent-dispatcher` 和 `multi-agent-orchestrator` 的迁移说明。
- 保留 Direct、Lite、Full 三种执行模式，Full Harness 仍作为高级持久化执行协议。

### v5.5.0

- 新增 wrapper-generated TDD trace 支持，用于运行验证命令并写入 TDD trace；当前入口为 `scripts/harness_test_run.py`。
- 扩展 `scripts/tdd_gate_check.py`，支持 strict TDD 循环的可选 `--source-path` mtime 校验。
- 在 run-state 模板和初始化输出中新增 `tdd_current_cycle_context`。
- 明确普通 worker 应优先使用 wrapper-generated trace evidence，而不是手写 TDD trace。
- 在 Bugfix Lane 和 Feature-Spec Lane 中加入 retry、checkpoint 和 rollback 规则，同时不允许在主工作区默认自动执行 `git reset --hard`。

### v5.4.0

- 新增 Bugfix Lane 和 Feature-Spec Lane，让开发流程按任务类型分流。
- 新增 `templates/tdd_trace.jsonl` 和 `scripts/tdd_gate_check.py`，用于运行时中立的 TDD 时间顺序校验。
- 更新 run 初始化和 runtime 打包流程，确保 TDD trace artifact 和 checker 脚本被包含。
- 收紧 sub-agent 和 evaluator 模板，要求记录 trace path、chronology summary、first production edit 和 unverified critical path。
- 扩展 eval cases，覆盖 code-before-RED、passing-test-as-RED、shell-bypass、UI-only-unit-test、self-report-only 和 missing no-test-reason 等失败模式。
- 新增 `.gitignore`，避免生成的 workspace、worktree 和 Python cache 文件污染版本库。

### v5.3.0

- 新增两层测试模型：`Test-First Evidence Gate` 和 `Strict TDD Gate`。
- 新增 `references/tdd-gates.md`，说明 RED/GREEN、替代验证和主代理验收规则。
- 在 sub-agent report 中新增必填的 `Test-First Or Substitute Verification` 字段。
- 在协议 JSON 记录中新增 `verification_gate`。
- 更新校验脚本，避免 sub-agent report 和协议记录完全绕过 testing gate 结构。

### v5.2.2

- 将英文和中文 README 重写为正式的公开项目文档。
- 明确项目定位、执行模式、安装流程、runtime 包边界和 Superpowers 借鉴声明。
- 未改变运行协议。

### v5.2.1

- 新增中英文公开文档。
- 明确声明对 Superpowers 相关工程方法的借鉴关系。
- 新增 `scripts/package_skill.py`，用于生成干净的 runtime-only 安装包。
- 在公开 README 中整理 Direct、Lite 和 Full 三种执行模式。
- 扩展 eval cases，覆盖 TDD 证据、审查分离、Superpowers 关系和干净分享包。

### v5.0.1

- 在 capability check 和 DAG 创建前新增 right-sizing gate。
- 明确多智能体措辞只代表授权评估，不代表自动调度。
- 增加小任务跳过 worker、worktree 和 artifact 的指导。

### v5.0.0

- 将项目从流程说明升级为由主代理执行的 harness 协议。
- 新增 capability snapshot、`run_state.json`、`acceptance_registry.json` 和 `trace.jsonl`。
- 新增 evaluator 校验，以及 Codex 和 Claude Code 风格运行时适配。

### v4.0.0

- 引入闭环多智能体协议。
- 新增 artifact 初始化、报告校验、角色边界、停止条件和 evaluator 模板。

---

## 许可证

当前仓库尚未包含 license 文件。
