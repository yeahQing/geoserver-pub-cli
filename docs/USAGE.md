# geoserver-pub-cli 操作手册

GeoServer 批量**图层发布**、**样式绑定**与**样式拉取**命令行工具（基于 PostGIS / db 模式）。

本手册覆盖 v0.3 的全部子命令：`layer`、`style`、`fetch`、`check`、`serve`，并给出可复制的完整示例。

---

## 目录

1. [运行方式](#1-运行方式)
2. [统一配置文件](#2-统一配置文件)
3. [通用连接参数](#3-通用连接参数)
4. [`layer` 发布图层](#4-layer-发布图层)
5. [`style` 发布样式并绑定](#5-style-发布样式并绑定)
6. [`fetch` 拉取样式（只读）](#6-fetch-拉取样式只读)
7. [`check` 核对发布状态（只读）](#7-check-核对发布状态只读)
8. [`serve` Web 可视化界面](#8-serve-web-可视化界面)
9. [跨平台打包](#9-跨平台打包)
10. [常见问题与注意事项](#10-常见问题与注意事项)
11. [版本历史](#11-版本历史)

---

## 1. 运行方式

工具提供三种等价的运行入口，命令参数完全一致：

| 方式    | 命令前缀                                     | 适用场景                 |
| ----- | ---------------------------------------- | -------------------- |
| 源码运行  | `python -m geopub`                       | 开发 / 调试              |
| 安装后   | `geopub`                                 | 已 `pip install -e .` |
| 打包单文件 | `./geopub`（Linux）/ `geopub.exe`（Windows） | 交付运维，零依赖             |

**安装（基础 + Web 界面）：**

```bash
cd geoserver-pub-cli
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip
pip install -e .              # 基础功能
pip install -e ".[web]"       # 额外启用 Web 界面（serve 命令）
```

**验证安装：**

```bash
geopub --help            # 或 python -m geopub --help
geopub serve --help      # 需已装 [web]
geopub --version         # 显示版本号（或 -V）
```

---

## 2. 统一配置文件

连接信息与各子命令默认值可写入配置文件，避免每次重复输入；命令行参数优先级更高。

### 2.1 自动探测顺序

```
--config 显式路径
  > 当前目录：geopub.toml / geopub.json / .geopub.toml / geopub.yaml / geopub.yml
  > 用户主目录：~/.geopub.toml
```

### 2.2 优先级

**命令行显式参数 > 配置文件 > 内置默认值。**

### 2.3 完整配置示例

复制为 `geopub.toml`（或 `.geopub.toml`）放到当前目录或用户主目录即可自动加载。也支持 `.json` / `.yaml`（yaml 需 `pip install pyyaml`）。

```toml
[geoserver]
url = "http://localhost:8080/geoserver"   # GeoServer 服务地址，必须带 /geoserver 后缀；HTTP/HTTPS 均可
user = "admin"                            # GeoServer 登录用户名（REST 发布/绑定需管理员权限）
password = "真实密码"                     # GeoServer 登录密码（明文，注意权限，见 §9；也可命令行 --password 传入）
workspace = "demo"                        # 工作空间名：图层与样式都会发布到该 workspace 下

[database]
host = "localhost"      # PostGIS 数据库主机 IP 或域名（图层数据的来源库）
port = 5432             # 数据库端口，PostgreSQL 默认 5432
dbname = "postgres"     # 数据库名（含待发布图层的那个库）
schema = "public"       # schema 名：待发布表所在的模式，默认 public
user = "postgres"       # 数据库用户名（需有该 schema 的读权限）
password = "真实密码"   # 数据库登录密码（明文，注意权限；也可命令行 --db-pass 传入）
store = "pg_store"      # GeoServer 数据存储(store)名称：不存在会自动创建；同一库建议固定一个 store 名

# 以下为各子命令默认值，均可被命令行覆盖
[layer]
file_path = ""      # 图层名清单文件路径（.xlsx 或 .csv）
column = "图层名"   # 文件中图层名列标题
all = false         # 是否发布 schema 下所有表

[style]
dir = ""         # SLD 文件目录
file_path = ""   # 样式-图层映射文件（可选，.xlsx 或 .csv）

[fetch]
out = "sld_output"   # SLD 输出目录：拉取的每个 .sld 落盘到此目录
file_path = ""       # 图层名清单文件路径（.xlsx 或 .csv，按 column 列读取）
column = "图层名"    # 文件中图层名列标题

[check]
out = "layer_check_result.csv"   # 结果 CSV 输出路径（核对已发布/未发布）
file_path = ""                   # 图层名清单文件路径（.xlsx 或 .csv，按 column 列读取）
column = "图层名"                # 文件中图层名列标题
deep = false                     # 识别「FeatureType 在、Layer 缺」的中间态
check_db = false                 # 追加「数据库表」列（需 database 段）
only_missing = false             # 结果 CSV 只输出未发布的图层
with_store = true                # 输出「数据存储」列（批量查 FeatureType）
with_style = false               # 输出「默认样式」列（逐图层查详情，较慢）
```

> 配置文件里的清单/映射参数名是 `file_path`（不是旧版的 `excel`）。命令行则主用 `--file-path`，并保留 `--excel` 作为兼容别名。

### 2.4 用配置简化命令

配置填好连接后，命令可大幅精简：

```bash
# 显式指定配置
geopub --config geopub.toml layer --file-path layer.xlsx
geopub --config geopub.toml style --dir ./styles
geopub --config geopub.toml fetch --layers "poi_point"
geopub --config geopub.toml serve --port 8000

# 若 geopub.toml 已在当前目录，连 --config 都可省略，自动加载
geopub layer --file-path layer.xlsx
geopub style --dir ./styles
```

---

## 3. 通用连接参数

下列参数**所有命令共享**，未传时回退到配置文件 / 默认值：

| 参数            | 说明                           | 默认      |
| ------------- | ---------------------------- | ------- |
| `--url`       | GeoServer 地址（含 `/geoserver`） | 必填（或配置） |
| `--user`      | 用户名                          | `admin` |
| `--password`  | 密码                           | 必填（或配置） |
| `--workspace` | 工作空间                         | `demo`  |

`layer` 与 `serve` 额外需要数据库连接参数（datastore）：

| 参数                                        | 说明              | 默认         |
| ----------------------------------------- | --------------- | ---------- |
| `--db-host`                               | PostGIS 主机      | 必填（或配置）    |
| `--db-port`                               | 端口              | `5432`     |
| `--db-name`                               | 数据库名            | `postgres` |
| `--db-schema`                             | schema          | `public`   |
| `--db-user`                               | 数据库用户           | `postgres` |
| `--db-pass`                               | 数据库密码           | 必填（或配置）    |
| `--store`（`layer`）/ `--db-store`（`serve`） | GeoServer 数据存储名 | `pg_store` |

---

## 4. `layer` 发布图层

把 PostGIS 表注册为 GeoServer 图层。

### 4.1 用法

```bash
geopub layer [通用连接参数] [db 参数] [--file-path 路径（或 --excel） --column 标题] [--all] [--interactive] [--store 名]
```

- `--file-path`（`--excel` 兼容别名）+ `--column`：按文件列读取图层名清单发布（**推荐**）。支持 `.xlsx` 与 `.csv`。
- `--all`：发布该 schema 下所有基表（与 `--file-path` 互斥，不传则按 `--file-path`，都没给则报错）。
- `--interactive`：列出候选项，交互勾选后再发布。

### 4.2 示例 1：用文件名单发布

```bash
geopub layer \
  --url "http://localhost:8080/geoserver" \
  --user admin --password 'YOUR_PASSWORD' \
  --workspace demo --store pg_store \
  --db-host localhost --db-port 5432 \
  --db-name gis --db-schema public \
  --db-user postgres --db-pass 'YOUR_PASSWORD' \
  --file-path "./data/layer.xlsx" --column "图层名"
```

### 4.3 示例 2：发布整个 schema（--all）

```bash
geopub layer \
  --url "http://localhost:8080/geoserver" \
  --user admin --password 'YOUR_PASSWORD' \
  --workspace demo --store pg_store \
  --db-host localhost --db-name gis \
  --db-pass 'YOUR_PASSWORD' \
  --all
```

### 4.4 示例 3：交互勾选（--interactive）

```bash
geopub layer \
  --url "http://localhost:8080/geoserver" \
  --user admin --password 'YOUR_PASSWORD' \
  --workspace demo --store pg_store \
  --db-host localhost --db-name gis --db-pass 'YOUR_PASSWORD' \
  --file-path "./data/layer.xlsx" --interactive
```

运行后会列出文件中的图层名，用空格勾选（方向键移动、空格选中、回车确认）后再执行发布。

### 4.5 示例 4：配合配置文件最简

假设 `geopub.toml` 已填好连接，`layer.xlsx` 也在当前目录：

```bash
geopub --config geopub.toml layer --file-path layer.xlsx
# 或 geopub.toml 已在当前目录时：
geopub layer --file-path layer.xlsx
```

### 4.6 示例 5：Windows PowerShell 含特殊字符密码

密码含 `$ & * ( ?` 等字符时，用**单引号**包裹（PowerShell 单引号是逐字字符串）：

```powershell
geopub layer \
  --url "http://localhost:8080/geoserver" \
  --user admin --password 'YOUR_PASSWORD' \
  --workspace demo --store pg_store \
  --db-host localhost --db-name gis --db-pass 'YOUR_PASSWORD' \
  --file-path "D:\gis\layer.xlsx" --column "图层名"
```

### 4.7 行为说明

- **datastore 自动创建**：若指定的 `--store` 在 GeoServer 中不存在，会自动创建（`ExposePrimaryKeys=true`）。
- **幂等**：已存在的图层会**跳过**（状态 `skipped`），不会重复创建。
- **坐标系**：图层默认 `EPSG:4326`。
- **返回结构（每行一个 JSON，供自动化解析）**：

```json
{"layer": "poi_point", "status": "ok", "detail": "发布成功"}
{"layer": "site_polygon", "status": "skipped", "detail": "已存在"}
{"layer": "bad_table", "status": "failed", "detail": "发布失败"}
```

---

## 5. `style` 发布样式并绑定

把 SLD 推上 GeoServer，并**绑定**为图层默认样式（这是"绑定"真正发生的地方）。

### 5.1 用法

```bash
geopub style [通用连接参数] --dir <SLD目录> [--file-path 映射文件（或 --excel）] [--interactive]
```

- `--dir`：递归扫描该目录下所有 `.sld` 文件。
- `--file-path`（`--excel` 兼容别名）：样式-图层映射文件（一对多）。**不传则按"同名图层"回退绑定**。
- `--interactive`：列出 `.sld` 文件，交互勾选后再发布。

### 5.2 示例 1：同名回退（不带 --file-path）

每个 `xxx.sld` 自动尝试绑定到同名图层 `xxx`；图层不存在则告警跳过。

```bash
geopub style \
  --url "http://localhost:8080/geoserver" \
  --user admin --password 'YOUR_PASSWORD' \
  --workspace demo \
  --dir "./data/styles"
```

### 5.3 示例 2：文件一对多映射绑定

一个样式可对应多个图层（样式在映射表中分多行出现）。

```bash
geopub style \
  --url "http://localhost:8080/geoserver" \
  --user admin --password 'YOUR_PASSWORD' \
  --workspace demo \
  --dir "./data/styles" \
  --file-path "./data/style_mapping.xlsx"
```

### 5.4 示例 3：交互勾选样式

```bash
geopub style \
  --url "http://localhost:8080/geoserver" \
  --user admin --password 'YOUR_PASSWORD' \
  --workspace demo \
  --dir "./data/styles" --interactive
```

### 5.5 示例 4：配合配置文件最简

```bash
geopub --config geopub.toml style --dir ./styles --file-path ./style_mapping.xlsx
```

### 5.6 映射文件格式

首行为表头（自动跳过），其后每行两列，**一对多**（同一样式可分多行对应多个图层）：

| 样式名（可带 .sld）   | 图层名         |
| -------------- | ----------- |
| road_style.sld | highway     |
| road_style.sld | local_road  |
| water          | river_layer |

- 样式名列可带或不带 `.sld` 后缀，工具都会识别。
- 未配置映射时自动回退到同名图层。

### 5.6.1 CSV 等价格式（服务器推荐）

`.xlsx` 在 Linux 服务器上编辑不便，**所有 `--file-path`（兼容 `--excel`）参数现在同时支持 `.csv` 文本文件**，命令写法完全不变——把文件名换成 `.csv` 即可。CSV 用纯文本，服务器上 `vi`/`nano` 直接编辑，且与 Excel 零成本互转（Excel「另存为 CSV」即可）。

- **样式-图层映射 CSV**（`style --file-path xxx.csv`，首行表头，两列：样式名,图层名）：

```csv
样式名,图层名
poi_pointnt,poi_point
point_test,city_layer
road_style.sld,highway
road_style.sld,local_road
```

- **图层名清单 CSV**（`layer` / `fetch --file-path xxx.csv`，首行表头，按 `--column` 取列，默认列名 `图层名`）：

```csv
图层名
city_layer
poi_point
```

项目已附示例：`config/style_mapping.example.csv`、`config/layer_names.example.csv`，复制改名即可用。

> 注意事项
> - CSV 读取兼容 Excel 导出的 BOM（`utf-8-sig`），但服务器手写建议保存为无 BOM 的 UTF-8。
> - 字段含逗号时用英文双引号包裹（标准 CSV 转义），工具已按 CSV 规范解析。
> - 旧 `.xlsx` 文件继续可用，无需迁移；同一台机器上 `.xlsx` 与 `.csv` 可混用。
> - 命令行参数主名为 `--file-path`；旧的 `--excel` 作为**兼容别名**保留（接收 .xlsx/.csv），旧脚本不受影响。

### 5.7 行为说明

- **发布/更新**：`existsStyle` 已存在则更新，否则新建。
- **绑定**：对每个目标图层 `configureLayer` 设置默认样式（PUT `/layers/{layer}`）；图层不存在则跳过（状态 `skipped`）。
- **返回结构**：

```json
{"style": "road_style", "publish": "created", "targets": ["highway", "local_road"],
 "binds": [
   {"layer": "highway", "status": "ok", "detail": "已绑定"},
   {"layer": "local_road", "status": "ok", "detail": "已绑定"}
 ]}
{"style": "water", "publish": "updated", "targets": ["river_layer"],
 "binds": [{"layer": "river_layer", "status": "skipped", "detail": "图层不存在"}]}
```

---

## 6. `fetch` 拉取样式（只读）

批量把每个图层的**默认样式 SLD** 下载到本地目录，并产出汇总报告。**只读，不写 GeoServer。**

### 6.1 用法

```bash
geopub fetch [通用连接参数]
  (--layers "a,b,c" | --file-path 路径 [--column 标题])
  [--out 输出目录] [--report 报告路径] [--list]
```

- 两种图层来源可组合、自动去重：**推荐 `--file-path`**（文件清单，维护一列图层名即可，最省事，支持 .xlsx/.csv）> `--layers`（直接列名）。
- `--list`：只列出将处理的图层，**不下载**（预览用）。
- `--out`：SLD 落盘目录，默认 `sld_output`。

### 6.2 示例 1：--layers 指定

```bash
geopub fetch \
  --url "http://localhost:8080/geoserver" \
  --user admin --password 'YOUR_PASSWORD' \
  --workspace demo \
  --layers "poi_point,gsm_site" \
  --out "./sld_output"
```

### 6.3 示例 2：--file-path 名单

```bash
geopub fetch \
  --url "http://localhost:8080/geoserver" \
  --user admin --password 'YOUR_PASSWORD' \
  --workspace demo \
  --file-path "./data/layer.xlsx" --column "图层名" \
  --out "./sld_output"
```

### 6.4 示例 3：--list 预览（不下载）

```bash
geopub fetch \
  --url "http://localhost:8080/geoserver" \
  --user admin --password 'YOUR_PASSWORD' \
  --workspace demo \
  --layers "poi_point,gsm_site" --list
```

### 6.5 示例 4：配合配置文件最简（推荐 --file-path）

推荐用 **文件清单**（`--file-path`）作为图层来源：只需在文件里维护一列图层名，服务器上用 CSV 还能直接 `vi` 编辑。假设 `geopub.toml` 已填好 `[geoserver]` 与 `[fetch]`：

```bash
geopub --config geopub.toml fetch --file-path layer.xlsx --column "图层名"
# 若 geopub.toml 已在当前目录，连 --config 都可省略；out 也用配置里的默认 sld_output：
geopub fetch --file-path layer.xlsx
```

- 连接参数（`--url/--user/--password/--workspace`）全部来自 `[geoserver]`。
- 图层清单（`--file-path` + `--column`）与输出目录（`--out`，默认 `sld_output`）来自 `[fetch]`。
- `fetch` 不会读取 `[database]` 段（只读 GeoServer，不碰 PostGIS），配置里有也无害。

### 6.6 输出与报告

- 每个图层生成 `{out}/{图层名}.sld`（UTF-8 文本）。
- 同时写 `{out}/_sld_report.json`（可用 `--report` 自定义路径）：

```json
{
  "summary": {"ok": 2, "skipped": 1, "failed": 0},
  "records": [
    {"layer": "poi_point", "status": "ok", "style": "poi_point", "detail": "1234 bytes -> poi_point.sld"},
    {"layer": "no_style_layer", "status": "skipped", "style": null, "detail": "图层无默认样式"},
    {"layer": "bad_layer", "status": "failed", "style": null, "detail": "HTTPError: 404"}
  ]
}
```

- `status` 取值：`ok`（已下载）/ `skipped`（无默认样式等）/ `failed`（取样式失败）。

### 6.7 只读说明

`fetch` **只读取并保存 SLD**，不会发布、更新或替换任何 GeoServer 上的样式，可反复安全运行。

---

## 7. `check` 核对发布状态（只读）

按 CSV/清单核对**哪些图层已经发布、哪些没发布**，结果写入 CSV。**只读，不写 GeoServer。**

典型场景：手上有一份几百行的图层清单，发版前先核对一遍，缺哪些一目了然；输出 CSV 过滤出「未发布」行，即为下次 `geopub layer` 的输入清单。

### 7.1 用法

```bash
geopub check [通用连接参数]
  (--layers "a,b,c" | --file-path 路径 [--column 标题])
  [--out 结果CSV] [--only-missing] [--deep] [--check-db] [db 参数]
```

| 参数 | 说明 | 默认 |
| --- | --- | --- |
| `--layers` | 逗号分隔的图层名列表 | 无 |
| `--file-path`（`--excel` 兼容别名） | 图层名清单文件（.xlsx / .csv，首行表头） | 无 |
| `--column` | 清单文件中图层名列标题 | `图层名` |
| `--out` | 结果 CSV 输出路径 | `layer_check_result.csv` |
| `--only-missing` | 结果只输出未发布的图层 | `False` |
| `--check-db` | 追加「数据库表」列（需 db 参数） | `False` |
| `--deep` | 识别「FeatureType 在、Layer 缺」中间态 | `False` |
| `--with-store` / `--no-store` | 输出 / 不输出「数据存储」列 | `True` |
| `--with-style` / `--no-with-style` | 输出 / 不输出「默认样式」列（逐图层查，较慢） | `False` |

> 只有 `--check-db` 需要数据库参数（`--db-host` 等）；其余开关仅走 GeoServer。

### 7.2 示例 1：基础核对（最常用）

```bash
geopub check \
  --url "http://localhost:8080/geoserver" \
  --user admin --password 'YOUR_PASSWORD' \
  --workspace demo \
  --file-path "./data/layer.csv" --column "图层名" \
  --out "./data/layer_check_result.csv"
```

终端输出：

```text
待核对图层 6 个，结果将写入 ./data/layer_check_result.csv

==================================================
检查方式：全量清单比对（服务端共 412 个图层）
清单条目：6
  已发布：4
  未发布：2
结果 CSV：./data/layer_check_result.csv（6 行）
未发布图层：never_published, 库中不存在的表
```

### 7.3 示例 2：只输出未发布的（可直接当发布清单）

```bash
geopub check --url ... --workspace demo \
  --file-path "./data/layer.csv" \
  --only-missing --out "./data/todo_layers.csv"
```

### 7.4 示例 3：深度核对（区分「没表」与「没发布」）

```bash
geopub check \
  --url "http://localhost:8080/geoserver" \
  --user admin --password 'YOUR_PASSWORD' \
  --workspace demo --store pg_store \
  --db-host localhost --db-port 5432 \
  --db-name gis --db-schema public \
  --db-user postgres --db-pass 'YOUR_PASSWORD' \
  --file-path "./data/layer.csv" \
  --check-db --deep \
  --out "./data/layer_check_result.csv"
```

### 7.5 输出 CSV 格式

编码 `utf-8-sig`（带 BOM），**Excel 双击直接打开不乱码**。

**列按开关动态输出，不会出现一整列空白。** 默认输出：

| 序号 | 图层名 | 发布状态 | 数据存储 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | poi_point | 已发布 | pg_store | 已发布 |
| 2 | broken_layer | 未发布 | | 未发布 |
| 3 | ghost_table | 未发布 | | 未发布 |

| 开关 | 对 CSV 的影响 |
| --- | --- |
| `--check-db` | 追加「数据库表」列（`存在` / `不存在`） |
| `--with-style` | 追加「默认样式」列（逐图层查详情，较慢） |
| `--no-store` | 去掉「数据存储」列 |
| `--deep` | 不新增列，仅在「备注」中标出可自愈的中间态 |

加上 `--check-db --with-style` 后的完整形态：

| 序号 | 图层名 | 发布状态 | 默认样式 | 数据存储 | 数据库表 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | poi_point | 已发布 | poi_point | pg_store | 存在 | 已发布 |
| 2 | broken_layer | 未发布 | | | 存在 | 未发布（FeatureType 已存在但 Layer 缺失，重跑 layer 可自愈） |
| 3 | ghost_table | 未发布 | | | 不存在 | 未发布（数据库中无此表，无法发布） |

- `数据存储`：默认输出，批量查 FeatureType 得到（1 + store 数 次请求），能一眼看出图层挂在哪个库。
- `备注`：未发布时给出可执行结论——**「库中无表」优先于「FeatureType 缺失」**，因为表不存在才是根因。

### 7.6 判定方式（性能与健壮性）

- **默认（catalog 模式）**：1 次 `GET /rest/workspaces/{ws}/layers.json` 拉全量图层做集合比对。几百行清单也是 1 个请求。
- **自动降级（probe 模式）**：若该端点返回 403/404/500（部分实例关闭了图层列表权限），自动改为逐个 `exists_layer` 探测，**任何环境都能出结论**，终端会明确提示已降级。
- **名称归一化**：清单里写 `poi_point` 或 `demo:poi_point` 都能正确匹配（GeoServer 各版本返回的 `name` 形态不一致，工具统一剥掉 `workspace:` 前缀再比对）。
- **两种模式下 store / 样式都能填上**：附加维度不依赖主判定方式，降级时结论一致。

### 7.7 为什么「默认样式」默认不输出

GeoServer 的图层**列表**端点是精简版，只返回 `name` + `href`，**不含** `defaultStyle` 与 `resource`：

```json
// GET /rest/workspaces/test/layers.json —— 每个条目只有这两项
{ "name": "sample_point",
  "href": ".../layers/sample_point.json" }
```

而单图层**详情**端点才带样式与资源：

```json
// GET /rest/workspaces/test/layers/{name}.json
{ "layer": { "name": "...", "type": "VECTOR",
             "defaultStyle": { "name": "test:sample_point", ... },
             "resource": { "name": "test:sample_point", ... } } }
```

因此：

| 字段 | 获取方式 | 请求数 | 默认 |
| --- | --- | --- | --- |
| 是否已发布 | 图层列表端点 | 1 | ✅ 开 |
| 数据存储 | FeatureType 列表端点的 `href` 里含 store 名，可批量 | 1 + store 数 | ✅ 开 |
| 默认样式 | 只能逐图层查详情端点 | N（清单长度） | ❌ 关（`--with-style` 开启） |

即：**不是拿不到，而是不值得为它付 N 次请求**。若清单只有十几行且需要核对样式绑定，`--with-style` 打开即可。

### 7.7 行为说明

- **只读**：不发布、不修改、不删除任何图层与样式，可反复安全运行。
- **典型工作流**：`check --only-missing` → 得到待发布清单 → `geopub layer --file-path 该清单` → 再 `check` 复核。
- **`--deep` 的价值**：GeoServer 删 Layer 时**不级联删 FeatureType**，会留下「FeatureType 在、Layer 缺」的中间态，此时图层查不到（判为未发布）但直接重跑 `geopub layer` 能自愈恢复。`--deep` 把这类单独标出来，避免误判为"表不存在"。

---

## 8. `serve` Web 可视化界面

启动本地 Web 服务，在浏览器中可视化完成上述所有操作。需已安装 `fastapi`/`uvicorn`（见 §1 安装）。

### 8.1 启动示例

```bash
geopub serve \
  --url "http://localhost:8080/geoserver" \
  --user admin --password 'YOUR_PASSWORD' \
  --workspace demo \
  --db-host localhost --db-name gis --db-pass 'YOUR_PASSWORD' \
  --port 8000
# 浏览器打开 http://127.0.0.1:8000
```

配合配置文件（连接信息自动预填）：

```bash
geopub --config geopub.toml serve --port 8000
```

### 8.2 页面功能

- **连接配置**：填写 GeoServer 与数据库地址。
- **测试连接**：验证可达性。
- **列出数据库表**：查看该 schema 下的表，作为发布清单参考。
- **图层发布**：按文件 / 全部 / 手动列表三种模式发布。
- **样式发布与绑定**：选 SLD 目录与可选映射文件后执行。
- **样式拉取**：指定图层清单后下载 SLD（含"仅列出"开关）。
- **发布状态核对**：按 CSV/清单核对哪些图层已发布、哪些没发布，结果输出 CSV（含"只输出未发布""同时核对数据库表""深度核对"三个开关）。

所有动作复用与 CLI 完全相同的核心逻辑，结果以 JSON 展示。


### 8.3 HTTP API（可供脚本/前端调用）

| 方法   | 路径                   | 说明                | 请求体                                                                                          |
| ---- | -------------------- | ----------------- | -------------------------------------------------------------------------------------------- |
| GET  | `/api/health`        | 健康检查              | —                                                                                            |
| GET  | `/api/config`        | 当前连接配置（密码仅返回是否设置） | —                                                                                            |
| POST | `/api/test`          | 测试 GeoServer 连通性  | —                                                                                            |
| GET  | `/api/tables`        | 列出数据库表            | —                                                                                            |
| POST | `/api/layer/publish` | 发布图层              | `{"mode":"file\|all\|list","file_path":路径,"column":"图层名","tables":[]}`                        |
| POST | `/api/style/publish` | 发布并绑定样式           | `{"style_dir":路径,"file_path":路径或null}`                                                       |
| POST | `/api/fetch`         | 拉取样式              | `{"layers":[],"file_path":路径,"column":"图层名","out":"sld_output","list_only":false}`            |
| POST | `/api/check`         | 核对图层发布状态（输出 CSV） | `{"layers":[],"file_path":路径,"column":"图层名","out":"layer_check_result.csv","deep":false,"check_db":false,"only_missing":false}` |

**curl 调用示例：**

```bash
# 测试连接
curl -X POST http://127.0.0.1:8000/api/test

# 列出数据库表
curl http://127.0.0.1:8000/api/tables

# 按文件发布图层
curl -X POST http://127.0.0.1:8000/api/layer/publish \
  -H "Content-Type: application/json" \
  -d '{"mode":"file","file_path":"./data/layer.xlsx","column":"图层名","tables":[]}'

# 发布并绑定样式
curl -X POST http://127.0.0.1:8000/api/style/publish \
  -H "Content-Type: application/json" \
  -d '{"style_dir":"./data/styles","file_path":"./data/style_mapping.xlsx"}'

# 拉取样式（仅列出）
curl -X POST http://127.0.0.1:8000/api/fetch \
  -H "Content-Type: application/json" \
  -d '{"layers":["poi_point"],"out":"sld_output","list_only":true}'

# 核对发布状态（只输出未发布的）
curl -X POST http://127.0.0.1:8000/api/check \
  -H "Content-Type: application/json" \
  -d '{"file_path":"./data/layer.csv","column":"图层名","out":"./data/check_result.csv","only_missing":true}'
```

---

## 9. 跨平台打包

将工具打包为单文件可执行程序（零依赖交付），详细步骤见 `README.md §5`。要点：

- **PyInstaller 不能交叉编译**：Windows 包在 Windows 构建，Linux 包在 Linux 构建。
- **推荐用 `uv`**（CentOS 7 等老系统首选，`uv` 自带 CPython 下载，自动拉 3.11）：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
cd geoserver-pub-cli
uv python install 3.11
uv venv --python 3.11 && source .venv/bin/activate
uv pip install ".[web,build]"
python scripts/build.py        # 产出 dist/geopub（Linux）/ dist/geopub.exe（Windows）
```

- **兼容性**：在 CentOS 7（glibc 2.17）上构建的二进制可运行于 CentOS 7 及所有更新的 Linux；反之 Ubuntu 构建的跑不了 CentOS 7。**目标机含老系统就在老系统上构建**。
- **CI 自动构建**：`.github/workflows/build.yml` 在 `ubuntu / windows / macos` 三平台矩阵产出 Artifact，打 `v*` 标签或手动触发即可下载三平台包。

---

## 10. 常见问题与注意事项

- **密码特殊字符**：命令行中密码含 `$ & * ( ?` 等，用**单引号**包裹（bash / PowerShell 均适用）。双引号会触发 bash 变量展开（如 `$d` 被替换为空），密码悄悄少字符、认证报 401——这是最常见的人为故障。
- **TOML 中的 Windows 路径**：TOML 双引号串里 `\` 是转义符，直接粘贴资源管理器复制的 `D:\a\b` 会报 `TOMLDecodeError: Unescaped '\'`。改用正斜杠 `D:/a/b`（推荐，跨平台）或单引号字面量 `file_path = 'D:\a\b'`。
- **相对路径基准**：CLI 与 Web 界面填写的相对路径均按**启动命令时所在目录（CWD）**解析（不是 exe 所在目录，也不是配置文件所在目录）。从 dist 目录启动 `geopub.exe serve` 时填 `config/xx.csv` 实际找的是 `dist/config/xx.csv`。跨目录启动建议一律填绝对路径。
- **Tomcat 加固导致绑定 403**：目标 GeoServer 的 Tomcat 若在 `web.xml` 的 `security-constraint` 中对 `PUT/DELETE` 配了空 `<auth-constraint/>`（拒绝所有用户），CLI 绑定默认样式会 403。判别方法：403 响应体是 Tomcat 的 HTML 页面而非 GeoServer 的 XML。修复：删掉 `<http-method>PUT</http-method>`、`<http-method>DELETE</http-method>` 两行后重启 Tomcat；放开后认证仍由 GeoServer BASIC auth + admin 角色把关，不会裸奔。
- **配置文件明文密码**：`geopub.toml` 含明文密码，请设权限 `chmod 600 geopub.toml` 并加入 `.gitignore`，避免提交到仓库。
- **幂等**：已存在的图层 / 样式会跳过或更新，不会重复创建；可放心重跑。
- **样式同名回退**：`style` 未给 `--file-path` 时，自动尝试绑定同名图层；图层不存在则告警跳过（不影响其他样式）。
- **`fetch` 为只读**：只下载 SLD，不发布 / 不替换样式，可反复运行。
- **坐标系**：图层默认 `EPSG:4326`，如需自定义在 `client.publish_db_layer` 调整。
- **Web 依赖为可选**：未安装 `fastapi/uvicorn` 时，其余 CLI 子命令仍可用，`serve` 会提示 `pip install "geopub[web]"`。
- **仅 db 模式**：本期未实现 shp 模式，仅支持 PostGIS 表发布。
- **REST 端点一致性**：封装路径与 GeoServer 官方 REST 一致；首次对接目标实例，建议先对单图层 / 单样式实测。

## 11. 版本历史

各版本的新增、变更与修复详见项目根目录 [CHANGELOG.md](../CHANGELOG.md)。运行 `geopub --version`（或 `-V`）可查看当前版本。
