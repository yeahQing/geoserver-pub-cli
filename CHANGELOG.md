# 更新日志

版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。当前版本见 `src/geopub/__init__.py` 的
`__version__`，也可运行 `geopub --version` 查看。

---

## [0.1.0] — 2026-10-22

首个开源版本。

### 命令

- **`geopub layer`**：把 PostGIS 表批量发布为 GeoServer 图层。自动确保数据存储（store）存在，
  按清单文件（`.xlsx` / `.csv`，`--file-path` + `--column`）或 `--all` 全量取表，幂等发布；
  `--interactive` 支持交互勾选。
- **`geopub style`**：递归扫描 SLD 目录批量发布样式并绑定为图层默认样式。有映射文件时按映射
  绑定（支持一对多样式→多图层），无映射文件时按同名图层回退绑定。
- **`geopub fetch`**：批量只读拉取图层默认样式 SLD 落盘（`{out}/{layer}.sld` + `_sld_report.json`
  汇总）。图层来源支持 `--layers` 逗号列表与 `--file-path` 清单，`--list` 只预览不下载。
- **`geopub check`**：按清单核对图层发布状态，输出 CSV。支持 `--only-missing`（只输出未发布的，
  可直接作为下次 `layer` 的输入）、`--check-db`（额外核对 PostGIS 表是否存在）、`--deep`
  （识别「FeatureType 在、Layer 缺」的中间态）、`--with-store` / `--with-style`（补充数据存储与
  默认样式列）。**纯只读**，可反复运行。
- **`geopub serve`**：启动本地 Web 界面（FastAPI + 离线单页，默认 `127.0.0.1:8000`），
  覆盖连接测试、列出数据库表、图层发布、样式绑定、样式拉取、发布状态核对；复用 CLI 同一套内核。

### 配置

- 统一配置文件支持 `.toml` / `.json` / `.yaml`（yaml 需 `pyyaml`），自动探测顺序为
  `--config` 指定 > 当前目录 > 用户主目录；优先级为 **命令行参数 > 配置文件 > 内置默认值**。
- 清单/映射文件按扩展名自动识别 `.xlsx` / `.xls` / `.csv`（CSV 按 `utf-8-sig` 读取，
  兼容 Excel 导出的 BOM），命令写法不变。
- 全局 `--version` / `-V`，先于配置加载执行。

### 打包与 CI

- `scripts/build.py`：PyInstaller 单文件打包，自动注入 Web 静态资源与 hidden-imports；
  构建前卸载 site-packages 中可能残留的旧副本（否则会打进陈旧代码），每次使用独立临时
  `--workpath` 避免复用分析缓存。
- GitHub Actions：`build.yml` 在推送 `v*` 标签时于 ubuntu / windows / macos 三平台矩阵构建并
  发布到 Release；`test.yml` 在 push / PR 时跑 Python 3.11 / 3.12 / 3.13 矩阵测试。
- 注意 PyInstaller **不能交叉编译**，且 Linux 产物绑定构建机的 glibc —— 目标机含老系统时应在
  老系统上构建。

### 兼容性处理（实机踩坑）

以下是开发过程中实测遇到并已规避的问题，改动相关代码前建议先读一遍：

- **存在性检查触发服务端 500**：裸 `GET /rest/.../{name}` 在部分 GeoServer 2.x 上会因
  `No converter for [RestWrapperAdapter]` 崩溃，导致整批发布在第一步中断。改为
  `GET .../{name}.json` + `Accept: application/json`。
- **样式更新不能走 DELETE + POST**：`DELETE` 会被 `403 Can't delete style referenced by existing
  layers` 拦死。改为 `PUT .../styles/{name}?raw=true` 原地重写 SLD，404 时退化为 POST 新建，
  POST 撞 already exists 时再退化回 PUT，双向互备。
- **SLD 媒体类型随版本而变**：按 SLD 根元素 `version` 选择 `application/vnd.ogc.sld+xml`（1.0）
  或 `application/vnd.ogc.se+xml`（1.1.0）；遇 `No converter` 自动换另一种类型重试。上传前剥离
  UTF-8 BOM，否则 XML 解析报 `Content is not allowed in prolog`。
- **图层发布幂等自愈**：GeoServer 删除 Layer 时不会级联删除 FeatureType，重发会得到
  `500 already exists`。此时自动「删除 FeatureType 映射 + 重新发布」恢复（不动 PostGIS 表），
  状态记为 `recovered`。
- **`layers.json` 是精简版端点**：每条目只有 `name` + `href`，**不含** `defaultStyle` / `resource`
  —— 这两个字段只在单图层详情 `/layers/{name}.json` 里。因此「数据存储」列改由批量查
  FeatureType 填充（1 + store 数 次请求），「默认样式」列因只能逐图层查而默认关闭。
- **`resource` / `defaultStyle` 可能是 Python dict 的 repr 字符串**：部分实例把它序列化成
  `"{'@type': 'featureType', 'name': 'demo:pg_store.poi_point'}"` 而非 JSON 对象，直接按路径切分
  会把整段文本写进 CSV。`_resource_ref` 先用 `ast.literal_eval` 还原再取值，非法文本原样返回。
- **`workspace:` 前缀需归一化**：清单里写 `poi_point` 或 `demo:poi_point` 都应正确匹配，否则
  带前缀的名字拼进 URL 会 404、被误判为未发布。
- **全量清单端点可能被关闭**：`GET /rest/workspaces/{ws}/layers.json` 返回 403/404/500 时，
  `check` 自动降级为逐个探测，终端明确提示已降级，任何环境都能出结论。
- **错误详情提取**：GeoServer 未捕获异常经 Tomcat 渲染成 HTML 错误页时，按 `<b>Message</b>` /
  `<b>Description</b>` 定点提取根因，而非盲截前 N 个字符（页面样板会把真正的错误句挤到截断边界）。
- **运行日志自动脱敏**：`geopub.log` 记录完整启动命令行，但 `--password` / `--db-pass` 的值
  一律替换为 `***`，支持 `--password xxx` 与 `--password=xxx` 两种写法。

### 已知限制

- 仅实现 **db / PostGIS 模式**，尚未支持 shapefile 发布。
- Tomcat 加固环境中若 `web.xml` 对 `PUT` / `DELETE` 配置了全拒的 `security-constraint`，
  样式绑定会返回 403（GET / POST 不受影响），需在服务端放开这两个方法。
- 发布时坐标系固定为 `EPSG:4326`，暂未开放为参数。
- 空数据表发布的图层 bbox 会退化为 0（回退世界范围），已有可行方案待实现。
