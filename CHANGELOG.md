# 更新日志 (Changelog)

本文件记录 geopub 各版本的功能、新增、变更与修复。版本号遵循语义化版本（semver）。
当前版本：**0.3.0**（源码 `src/geopub/__init__.py` 的 `__version__`，可用 `geopub --version` 查看）。

---

## [0.3.0] — 2026-10-14

小版本：新增 `check` 子命令——按 CSV/清单核对哪些图层已发布、哪些没发布，结果输出 CSV（**只读**）。

### 新增

- **`geopub check` 核对发布状态**：读图层名清单（`--file-path` 兼容 `--excel`，支持 .xlsx/.csv，首行表头 + `--column` 指定列；也可 `--layers` 逗号列表，两者可合并去重），逐条判定是否已发布，结果写入 CSV。
  - **输出 CSV**（`--out`，默认 `layer_check_result.csv`），编码 `utf-8-sig`，**Excel 双击打开不乱码**。**列按开关动态输出，不会出现一整列空白**。
  - **判定方式自适配**：优先 1 次 `GET /rest/workspaces/{ws}/layers.json` 拉全量做集合比对（几百行清单也是 1 个请求）；该端点返回 403/404/500 时**自动降级**为逐个 `exists_layer` 探测，终端明确提示已降级，任何环境都能出结论。
  - **`--only-missing`**：结果只输出未发布的图层，可直接作为下次 `geopub layer` 的输入清单（核对 → 发布 → 复核）。
  - **`--check-db`**：额外核对 PostGIS 表是否存在，区分"库里有表只是没发布"与"库里根本没这张表"（后者无法发布，需先建表）。需 db 参数。
  - **`--deep`**：额外查 FeatureType 列表，识别"FeatureType 在、Layer 缺"这一 GeoServer 删 Layer 不级联删 FeatureType 的中间态（重跑 `geopub layer` 可自愈），避免误判为"表不存在"。需 db 参数。
  - **纯只读**：不发布/修改/删除任何图层与样式，可反复安全运行。
- **`client.list_layers` / `client.list_featuretypes` / `client.list_datastores` / `client.get_layer_style`**：新增只读清单查询端点，供 `check` 与后续审计类功能复用；`check` 的判定逻辑收敛在 `core.check_layers`，CLI 与 Web 共用同一套实现。
- **Web 端**：`POST /api/check` 接口 + 页面新增「发布状态核对」Tab（清单文件/图层名、输出路径、同时核对数据库表、深度核对、只输出未发布、查所属存储、查默认样式六个开关）。
- **`[check]` 配置段**：`out` / `file_path` / `column` / `deep` / `check_db` / `only_missing` / `with_store` / `with_style`，示例见 `geopub.example.toml`。

### 修复

- **「默认样式 / 数据存储」列恒为空**：实测（GeoServer 2.x）`GET /rest/workspaces/{ws}/layers.json` 是**精简版**端点，每条目只有 `name` + `href`，**不含** `defaultStyle` / `resource`（这两个字段只在单图层详情 `/layers/{name}.json` 里）。原实现从列表项解析这两个字段，必然全空。
  - `数据存储` 改为批量查 FeatureType（`client.list_featuretypes`），store 名从列表项 `href`（形如 `.../datastores/{store}/featuretypes/{name}.json`）中提取，1 + store 数 次请求即可填满整列，且不再依赖清单长度。
  - `默认样式` 因只能逐图层查详情（N 次请求），改为**默认关闭**，需显式 `--with-style` 才输出。
  - CSV 改为按开关动态拼列（`client`/`check.build_header` + `build_row`），杜绝整列空白。
- **`resource` / `defaultStyle` 返回 dict repr 字符串导致 store 列被污染**：实测部分 GeoServer 实例把这两个字段序列化成 Python dict 的 repr 字符串（`"{'@type': 'featureType', 'name': 'demo:pg_store.poi_point'}"`）而非 JSON 对象。旧逻辑直接按路径切分，导致结果 CSV 的「数据存储」列被写成整段 dict 文本（`'featureType', 'name': 'demo:pg_store`）。现由 `_resource_ref` 先用 `ast.literal_eval` 还原 dict 再取 `name`，并对非法文本原样返回而不抛异常。
- **带 `workspace:` 前缀的清单项在降级路径被误判为未发布**：`exists_layer` 直接把名字拼进 URL，`demo:poi_point` 会 404。现统一用剥掉前缀的裸名探测，与 catalog 模式结论保持一致。
- **URL 形式引用名切分错误**：`_strip_ws` 遇到含 `://` 的资源 URL 时会把 `http` 当工作空间名切错；`_split_ref` 现按"去查询串 → 取路径末段 → 去 .json/.xml 后缀 → 剥工作空间前缀 → 按最后一个点拆 store/table"的顺序处理。
- **`--deep` / `--check-db` 意外退化为逐个探测**：原先只要开启附加维度就跳过全量清单接口，白白多出 N 次请求。现两者仅作附加维度，不影响主判定方式。
- **`--deep` 不再依赖 db 参数**：FeatureType 数据已批量取得，`--deep` 单独使用即可（原先必须同时给 `--db-store`）。

### 变更

- 版本号 0.2.2 → 0.3.0（`__init__.py` 与 FastAPI 应用版本同步）。

---

## [0.2.2] — 2026-09-22

小版本：运行日志落盘。

### 新增

- **运行日志 `geopub.log`**：每次运行自动追加到**启动命令时所在目录**（UTF-8，记事本/vi 可直接看）。记录：启动命令行（**密码自动脱敏为 \*\*\***，支持 `--password xxx` 与 `--password=xxx` 两种写法）、每条图层的发布/跳过/失败结果、样式发布与绑定结果、fetch 汇总；失败项额外写入 **GeoServer 原始响应体**（4000 字符内不截断），任何控制台显示不全的错误都能在日志里找到完整原文。日志写失败静默吞掉，绝不影响主流程。
- 控制台在出现失败时提示日志文件位置。

---

## [0.2.1] — 2026-09-22

小版本：发布失败日志的可读性修复。

### 修复

- **错误详情被截断看不懂**：GeoServer 未捕获异常经 Tomcat 渲染为 HTML 错误页时，旧实现剥全部标签后固定取前 400 字符，页面样板（Type/Status 等，约 350 字符）把真正的 `<b>Message</b>` 根因句挤到截断边界，日志只剩半句（如 "Trying to create new feature type inside the store, but no"）。现按 `<b>Message</b>` / `<b>Description</b>` 定点提取完整根因；纯文本兜底截断放宽到 600 字符并加省略号标记。
- **图层发布 400 增加人话提示**：识别 "no table was found to extract the schema" 报错签名，失败详情追加定位提示（库/schema/store + 三步核对：表存在性、表名大小写、清单与目标环境一致性），CLI 与 Web 共用同一逻辑。

---

## [0.2.0] — 2026-09-11 ~ 2026-09-20

自 0.1.0 以来的第二轮大版本：配置文件、Web 界面、跨平台打包、REST 兼容性根治与参数语义化。

### 新增

- **统一配置文件**：支持 `geopub.toml` / `.json` / `.yaml`（yaml 需 pyyaml），自动探测（`--config` 显式路径 > 当前目录 > 用户主目录），优先级为 **命令行 > 配置文件 > 内置默认**；示例见 `geopub.example.toml`。
- **Web 可视化界面**（`geopub serve`，可选依赖 `[web]`）：FastAPI + 离线单页前端，提供测试连接、列出数据库表、图层发布、样式发布绑定、样式拉取（含"仅列出"预览）；复用 CLI 同一套核心逻辑。
- **跨平台打包**：`scripts/build.py`（PyInstaller 单文件，自动注入 web 静态资源与 hidden-imports；构建前自动卸载 site-packages 残留旧副本、每次使用独立临时 workpath，杜绝打进陈旧代码）+ GitHub Actions 三平台（ubuntu/windows/macos）矩阵构建，打 `v*` 标签即产出三个包。
- **CSV 清单支持**：所有清单/映射文件按扩展名自动识别 `.xlsx` / `.xls` / `.csv`（CSV 用 `utf-8-sig` 读取，兼容 Excel 导出的 BOM），命令写法不变；新增 `config/layer_names.example.csv`、`config/style_mapping.example.csv` 示例。
- **`--version` / `-V` 全局参数**：打印版本号并退出（is_eager，先于配置加载）。
- **layer 发布幂等自愈**：GeoServer 删 Layer 未级联删 FeatureType 导致的 `500 already exists`，自动"删 FeatureType 映射 + 重新发布"恢复（不动 PostGIS 表），状态记为 `recovered`。
- **SLD 版本探测**：按 SLD 根元素 `version` 自动选媒体类型（1.0 → `application/vnd.ogc.sld+xml`，1.1.0 → `application/vnd.ogc.se+xml`），遇 `No converter` 自动换另一种类型重试；上传前剥离 UTF-8 BOM。
- **examples/ 示例目录**：图层名清单、样式-图层映射的 xlsx 示例与生成脚本。
- **docs/USAGE.md / docs/BUILD.md**：覆盖四子命令完整示例与三平台打包方法。

### 变更（Breaking / 参数更名）

- **删除 `--manifest` 参数**：md 反引号图层清单（`parse_layers_from_md`）整套移除，fetch 图层来源仅保留 `--layers` 与 `--file-path`。
- **`--excel` 更名 `--file-path`**：三处子命令统一；保留 `--excel` 作为兼容别名。配置键同步 `excel` → `file_path`（`[layer]` / `[style]` / `[fetch]` 段），前端请求体字段同步更名。
- **版本号对齐**：`__version__` 自 0.1.0 升至 0.2.0（与文档自述一致），FastAPI 应用版本同步。

### 修复

- **REST 存在性检查 500（GeoServer 2.x 序列化 bug）**：样式/图层存在性探测由裸 `GET /rest/.../{name}` 改为 `GET .../{name}.json` + `Accept: application/json`，避开服务端 `No converter for [RestWrapperAdapter]` 崩溃（该崩溃曾导致整批样式发布在第一步即中断）。
- **样式更新路径走不通**：废弃 `DELETE + POST` 重建（DELETE 被 `403 Can't delete style referenced by existing layers` 拦死），改为 `PUT .../styles/{name}?raw=true` 原地重写 SLD（404 时退化为 POST 新建；POST 撞 already exists 时退化为 PUT，双向互备）。
- **错误体透出与批量不中断**：GeoServer 5xx 响应体（XML `<ExceptionText>` / JSON `message` / 纯文本截断）提取到结果 detail；layer/style/fetch 三子命令单条失败仅记 `failed` 并继续，不再整批裸崩。
- **style 命令失败被静默吞掉**：样式发布失败时打印原因并纳入汇总计数（此前只显示"成功 0 个"，真因丢失）。
- **绑定默认样式丢字段**：`configure_default_style` 改为 GET 全量 layer → 改 `defaultStyle` → PUT 整体回写，避免局部 PUT 偶发丢 resource。
- **fetch 报告路径 NameError**：`cli.py` 漏 `import os` 导致运行期崩溃，已补。
- **Web UI 拉取结果不显示**：结果区 `<pre id="f_out">` 与输出目录输入框 `<input id="f_out">` id 重复，`getElementById` 取到 input、JSON 写入 `textContent` 无效；结果区改为 `f_result`。
- **主配置 TOML 解析失败**：`config/geopub.toml` 中 Windows 反斜杠路径触发 `TOMLDecodeError: Unescaped '\'`，改用正斜杠（TOML 双引号串中 `\` 为转义符）。

### 已知事项（服务端环境，非工具缺陷）

- Tomcat 加固环境（如 35 线上）`web.xml` 对 `PUT/DELETE` 配 `security-constraint` 全拒时，样式绑定会 403；需在该 Tomcat 放开 PUT/DELETE 后重启（认证仍由 GeoServer BASIC auth 把关）。详见操作手册 §9。
- 空数据表发布的图层 bbox 退化为 0 的问题（EPSG:4326 下回退世界范围）已分析可行，尚未实施。

---

## [0.1.0] — 2026-09-11

初始版本：独立 Python CLI（typer + httpx + openpyxl + questionary + psycopg2），仅实现 **db / PostGIS 模式**。

### 功能

- **`geopub layer`**：PostGIS 表批量发布为 GeoServer 图层——ensure datastore → 按名单（`--excel`）或 `--all` 全量取表 → 幂等发布；支持 `--interactive` 交互勾选。
- **`geopub style`**：递归扫描 SLD 目录批量发布样式并绑定为图层默认样式——映射文件（一对多）优先，否则同名回退绑定。
- **`geopub fetch`**：批量只读拉取图层默认样式 SLD 落盘（`{out}/{layer}.sld` + `_sld_report.json` 汇总）；支持 `--layers` / `--excel` / `--manifest` 三种清单来源与 `--list` 预览。
- 未实现 shp 模式。
