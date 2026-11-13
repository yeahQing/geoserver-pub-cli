# Tasks

## 1. 核心与 CLI

- [x] 1.1 `core.py`：`publish_styles()` 增加 `styles_only: bool = False` 参数，为 True 时跳过绑定循环、`targets=[]`、`binds=[]`，docstring 说明语义；验证：`pytest tests/test_style_publish.py -k core`
- [x] 1.2 `cli.py` `style_cmd`：新增 `styles_only: bool | None` 参数（`--styles-only/--no-styles-only`），经 `pick(CONFIG, "style", "styles_only", ...)` 合并；验证：`geopub style --help` 出现新标志
- [x] 1.3 `cli.py` `style_cmd`：合并后值上做互斥校验（styles_only 且 file_path 非空 → 红字报错 exit 1），校验位于 `_geo()` 之前；验证：CliRunner 测试 `--styles-only --file-path x.csv` 退出码非零且输出含「互斥」
- [x] 1.4 `commands.py` `style_publish()`：增加 `styles_only` 参数，置空 mapping、打印「仅上传模式：不绑定图层」、输出样式级汇总「新增 X / 更新 Y / 失败 Z」，不再输出绑定统计与「请先 geopub layer」提示；验证：pytest 中以假结果列表驱动渲染断言

## 2. Web 端

- [x] 2.1 `web.py`：`StylePublishIn` 增加 `styles_only: bool = False`，路由透传给 `core.publish_styles`；验证：`python -c "from geopub.web import StylePublishIn; StylePublishIn(style_dir='x', styles_only=True)"` 通过
- [x] 2.2 `web/static/index.html`：样式页增加「仅上传，不绑定图层」勾选框，请求体携带 `styles_only`；验证：serve 启动后页面元素存在（人工或 grep `s_only`）

## 3. 测试与文档

- [x] 3.1 新增 `tests/test_style_publish.py`（仿 `test_check.py` 的 FakeClient 离线模式）：仅上传模式不调用图层方法且 binds 为空；created/updated 判定；默认模式同名回退与映射一对多回归；CLI 互斥校验；验证：`pytest tests/test_style_publish.py` 全绿
- [x] 3.2 `geopub.example.toml` `[style]` 段加 `styles_only = false` 注释；`src/geopub/__init__.py` 版本升 `0.2.0`；验证：`geopub --version` 输出 0.2.0
- [x] 3.3 `docs/USAGE.md` §5 增加标志用法与「仅上传模式」小节、§8 API 表加字段、常见问题补充；`README.md` §2.3 示例与 §3 命令表更新；`CHANGELOG.md` 加 `## [0.2.0] — 2026-11-13`；验证：文档通读，示例命令与实际 `--help` 一致

## 4. 集成验证

- [x] 4.1 全量 `pytest` 与 `ruff check src tests` 通过；`geopub style --help`、`geopub --version` 冒烟正常；验证：命令输出无错误
- [x] 4.2 `openspec validate add-style-only-upload --strict` 通过；验证：命令退出码 0

## Workflow follow-up

- 全部任务完成后执行 `openspec archive` 将 delta 合入 `openspec/specs/style-publishing/spec.md`
- git commit 由用户另行决定，不在本变更范围内
