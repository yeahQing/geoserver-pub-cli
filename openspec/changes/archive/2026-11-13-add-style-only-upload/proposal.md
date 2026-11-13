# Proposal

## Why

`geopub style` 在上传 SLD 后总是尝试绑定图层：无映射时按「同名图层」回退（`core.publish_styles` 中 `targets = mapping.get(name) or [name]`），图层不存在时逐个打印「图层不存在」告警。用户需要一个显式的「仅上传/更新样式、完全不碰图层」的模式，用于预先批量上传样式或图层由其他流程管理的场景；当前只能靠忽略告警变通，输出噪音大且语义不明确。

## What Changes

- `geopub style` 新增 `--styles-only/--no-styles-only` 标志：仅发布/更新目录下全部 SLD，不做任何图层绑定（不查图层、不写默认样式），输出样式级汇总（新增/更新/失败）
- 标志支持配置文件 `[style].styles_only`，优先级沿用现有约定（CLI 显式值 > 配置文件 > 默认值）
- `--styles-only` 与 `--file-path`（含配置 `[style].file_path`）互斥，同时给出时报错退出
- 默认行为不变：不加标志时保持映射绑定与同名回退绑定
- Web 端同步：`POST /api/style/publish` 请求体新增可选 `styles_only` 字段，前端样式页新增「仅上传，不绑定图层」勾选框
- 版本升至 0.2.0

## Capabilities

### New Capabilities
- `style-publishing`: SLD 样式发布能力——上传/更新样式、样式-图层绑定、仅上传模式；覆盖 `geopub style` 命令与 Web 样式发布接口的可观察行为

### Modified Capabilities

## Impact

- `src/geopub/core.py`：`publish_styles()` 增加 `styles_only` 参数
- `src/geopub/cli.py`：`style_cmd` 增加标志、互斥校验
- `src/geopub/commands.py`：`style_publish()` 增加 `styles_only` 参数与两种汇总输出
- `src/geopub/web.py` + `src/geopub/web/static/index.html`：API 字段与前端勾选框
- `geopub.example.toml`、README、docs/USAGE.md、CHANGELOG、`__version__`
- 新增 `tests/test_style_publish.py`
