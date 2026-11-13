# Design

## Context

`geopub style` 的执行链路：CLI（`cli.py:style_cmd`）→ 业务命令（`commands.py:style_publish`，负责打印与汇总）→ 核心逻辑（`core.py:publish_styles`，返回结构化结果，被 CLI 与 Web 复用）。绑定行为发生在 `core.publish_styles`（core.py:252）：`targets = mapping.get(name) or [name]`，无映射时按同名图层回退。Web 端 `POST /api/style/publish`（web.py）与前端样式页（`web/static/index.html`）复用同一核心。配置合并统一走 `config.pick()`（CLI 显式值 > 配置文件 > 默认值），布尔配置项要求 `Optional[bool]` + `--x/--no-x` 形式（参见 `--all/--no-all`、`--deep/--no-deep`）。

## Goals / Non-Goals

**Goals:**
- 一个标志切换「仅上传」模式，语义清晰、默认行为零变化
- CLI 与 Web 共用同一核心参数，行为一致
- 与既有配置合并惯例完全兼容（支持 `[style].styles_only`）

**Non-Goals:**
- 不改变默认（绑定）行为，不做绑定方式重构
- 不引入按名单挑选样式的机制（目录发现 + `--interactive` 已覆盖）
- 不处理非 SLD 格式（Zip/GeoCSS/MbStyle）

## Decisions

### D1：在 `style` 命令上加 `--styles-only` 标志，而非新增子命令
「让现有命令支持一种模式」比拆出新命令更符合现有命令面（layer/style/fetch/check/serve），帮助文档、配置段均挂在同一命令下。备选的独立子命令 `style-upload` 会造成两条上传路径、两份汇总逻辑；改为绑定默认关闭（`--no-bind`）则是破坏性变更。**排除**。

### D2：核心开关放在 `core.publish_styles(styles_only: bool = False)`
仅上传模式的本质差异在核心层（跳过绑定循环），CLI 与 Web 只是传参。结果结构保持 `{"style", "publish", "targets", "binds"}` 键不变（`targets=[]`、`binds=[]`），CLI/Web 渲染代码无需分支适配。备选——在 commands 层拼接独立结果——会造成 CLI 与 Web 结果形状分叉。**排除**。

### D3：互斥校验在 CLI 层、`_geo()` 连接校验之前
`--styles-only` 与映射文件矛盾，属于参数级错误，应在发起任何 GeoServer 请求前失败；同时使 `typer.testing.CliRunner` 无需连接参数即可离线测试该校验。校验对象为合并后的最终值（含配置 `[style].file_path`）。Web 端不做硬互斥（前端勾选即隐藏映射输入框），API 层由核心逻辑自然忽略 mapping——避免 API 破坏性变更。

### D4：标志形式 `--styles-only/--no-styles-only`（`Optional[bool]`）
沿用 `pick()` 对布尔项的约定：需要区分「未传」与「显式 False」，才能支持配置文件 `styles_only = true` 且命令行可用 `--no-styles-only` 显式覆盖。

### D5：仅上传模式的汇总输出为样式级
默认模式现有四类计数（绑定成功/跳过/失败 + 样式发布失败）；仅上传模式只看样式本身，输出「新增 X / 更新 Y / 失败 Z」，并省略「请先 `geopub layer` 发布该表」提示（该提示与图层相关，仅上传模式下无意义且误导）。

## Risks / Trade-offs

- [结果结构保留空的 `targets`/`binds` 键，可能让调用方误以为有绑定语义] → 在 core docstring 与 USAGE.md 明确仅上传模式两键恒为空；Web 前端勾选后对应展示自然为空
- [配置文件里误配 `styles_only = true` 长期生效，用户疑惑为何不绑定] → 启动时打印「仅上传模式：不绑定图层」横幅提示（CLI 与 Web 响应均体现）
- [`--no-styles-only` 写法冗长] → 与 `--no-all`、`--no-deep` 既有惯例一致，保持一致性优先

## Migration Plan

纯增量功能，无迁移。回滚 = 移除标志（默认行为从未改变）。

## Open Questions

无。
