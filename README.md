# geopub · GeoServer 批量发布 CLI

[![build-binaries](https://github.com/yeahQing/geoserver-pub-cli/actions/workflows/build.yml/badge.svg)](https://github.com/yeahQing/geoserver-pub-cli/actions/workflows/build.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

把 **PostGIS 表批量发布为 GeoServer 图层**、**批量绑定 SLD 样式**、**批量拉取已有样式**、**核对发布状态** 的命令行工具。
一个 `geopub` 命令覆盖「发布 → 绑样式 → 核对 → 回捞」的完整闭环，适合几十到上千图层的一次性初始化与日常巡检。

- **CLI 优先**：`typer` + `rich`，交互式勾选、彩色进度、失败可重跑。
- **配置集中**：一份 `geopub.toml`（或 `.json` / `.yaml`）管好连接信息，命令行参数可临时覆盖。
- **可选 Web 界面**：`geopub serve` 起一个本地页面，不记命令也能操作。
- **可打包单文件**：PyInstaller 产出 Windows / Linux / macOS 免 Python 环境的可执行文件。
- **幂等 + 只读分离**：`layer` / `style` 可反复执行，`fetch` / `check` 纯只读，任何环境都能安全跑。

---

## 1. 安装

要求 **Python ≥ 3.11**（解析 TOML 配置用到标准库 `tomllib`）。

```bash
git clone https://github.com/yeahQing/geoserver-pub-cli.git
cd geoserver-pub-cli
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .

# 需要 Web 界面
pip install -e ".[web]"

# 需要自己打包单文件
pip install -e ".[build]"
```

安装后即可使用 `geopub` 命令；开发期也可 `python -m geopub ...`。

不想装 Python：直接到 [Releases](https://github.com/yeahQing/geoserver-pub-cli/releases) 下载对应平台的可执行文件。

## 2. 快速开始

### 2.1 写配置

```bash
cp geopub.example.toml geopub.toml
# 编辑 geopub.toml，填 GeoServer 地址、账号密码、PostGIS 连接
```

`geopub.toml` 可以放在**当前目录**、**用户主目录**（`~/.geopub.toml`），或用 `--config` 显式指定。
优先级：**命令行参数 > 配置文件 > 内置默认值**。

### 2.2 发布图层

```bash
# 按清单文件发布（.xlsx / .csv，按 --column 指定的列读取图层名）
geopub layer --file-path ./examples/layer_names.csv --column "图层名"

# 发布该 schema 下所有基表
geopub layer --all

# 交互式勾选（方向键移动、空格选中、回车确认）
geopub layer --all --interactive
```

### 2.3 绑定样式

```bash
# 按「样式-图层」映射文件绑定（支持一对多）
geopub style --dir ./styles --file-path ./examples/style_mapping.csv

# 不带映射文件时，自动按「同名图层」回退绑定
geopub style --dir ./styles
```

### 2.4 核对发布状态（只读）

```bash
geopub check --file-path ./examples/layer_names.csv --out ./result.csv

# 同时核对数据库表是否存在、识别 FeatureType 在但 Layer 缺的中间态
geopub check --file-path ./examples/layer_names.csv --check-db --deep

# 只输出未发布的，结果可直接作为下次 layer 的输入清单
geopub check --file-path ./examples/layer_names.csv --only-missing --out ./missing.csv
geopub layer --file-path ./missing.csv
```

结果 CSV 用 `utf-8-sig` 编码，Excel 双击打开不乱码；列按开关动态输出，不会出现整列空白。

### 2.5 回捞样式（只读）

```bash
geopub fetch --layers "poi_point,city_grid" --out ./sld_output
geopub fetch --file-path ./examples/layer_names.csv --list   # 只看会处理哪些图层
```

## 3. 命令一览

| 命令 | 作用 | 是否写 GeoServer |
|---|---|---|
| `geopub layer` | 发布 PostGIS 表为图层（支持自愈已存在的半成品） | 写 |
| `geopub style` | 上传 SLD 并绑定为图层默认样式 | 写 |
| `geopub fetch` | 批量下载图层默认样式 SLD | 只读 |
| `geopub check` | 按清单核对发布状态，输出 CSV | 只读 |
| `geopub serve` | 启动本地 Web 界面（默认 `127.0.0.1:8000`） | 取决于操作 |

完整参数、输出说明与排错见 **[docs/USAGE.md](./docs/USAGE.md)**。

## 4. 配置说明

```toml
[geoserver]
url = "http://localhost:8080/geoserver"   # 必须带 /geoserver 后缀
user = "admin"
password = "YOUR_PASSWORD"
workspace = "demo"

[database]
host = "localhost"
port = 5432
dbname = "gis"
schema = "public"
user = "postgres"
password = "YOUR_PASSWORD"
store = "pg_store"                        # 不存在会自动创建
```

其余 `[layer]` / `[style]` / `[fetch]` / `[check]` 段为各子命令默认值，全部可被命令行覆盖。
完整注释见 [`geopub.example.toml`](./geopub.example.toml)。

## 5. Web 界面（可选）

```bash
pip install -e ".[web]"
geopub serve                      # 浏览器打开 http://127.0.0.1:8000
```

页面提供连接测试、列出数据库表、图层发布、样式绑定、样式拉取、发布状态核对，
所有动作复用与 CLI 完全相同的内核逻辑。

## 6. 打包单文件可执行程序

```bash
pip install -e ".[build]"
python scripts/build.py                 # 产物在 dist/geopub（Windows 为 dist/geopub.exe）
python scripts/build.py my-tool         # 自定义产物名
```

推送 `v*` 标签会触发 GitHub Actions，在 `ubuntu` / `windows` / `macos` 三个 runner 上各产出一份并上传 Artifact。

> PyInstaller **不能交叉编译**，且 Linux 产物绑定构建机的 glibc。目标机含 CentOS 7 等老系统时，请在老系统上构建以扩大兼容面。
> 详见 **[docs/BUILD.md](./docs/BUILD.md)**。

## 7. 注意事项

- **密码特殊字符**：命令行里的 `$ & * ( ?` 等在 bash / PowerShell 中都要用**单引号**包裹（双引号会触发变量展开，导致认证 401）。
- **TOML 里的 Windows 路径**：双引号串中 `\` 是转义符，请用正斜杠 `D:/gis/layer.xlsx` 或单引号字面量 `'D:\data\layer.xlsx'`。
- **相对路径基准**：配置与命令里的相对路径都按**启动时所在目录（CWD）**解析，不是 exe 所在目录、也不是配置文件目录。
- **写作端点受限制的 Tomcat**：若目标 GeoServer 在 `web.xml` 对 `PUT`/`DELETE` 配了空 `<auth-constraint/>`，样式绑定会返回 403（GET/POST 不受影响）。需放开该约束。
- **配置文件含明文密码**：`chmod 600 geopub.toml`，并确认已被 `.gitignore` 忽略。
- **坐标系**：发布时默认 `EPSG:4326`，如需其他坐标系可修改 `client.publish_db_layer` 中的 `srs` / `nativeCRS`（也欢迎提 PR 做成参数）。
- **当前仅支持 db / PostGIS 模式**，shapefile 模式未实现。

## 8. 项目结构

```
geoserver-pub-cli/
├── src/geopub/
│   ├── cli.py          # typer 命令定义与参数合并
│   ├── client.py       # GeoServer REST 封装 + PostGIS 连接
│   ├── core.py         # 发布/绑定/拉取/核对的核心流程
│   ├── check.py        # 发布状态核对与 CSV 输出
│   ├── config.py       # 配置模型与多格式加载
│   ├── web.py          # FastAPI 应用（可选）
│   └── web/static/     # Web 界面静态页
├── docs/               # USAGE / BUILD / OPS
├── examples/           # 示例清单与映射文件
├── scripts/build.py    # PyInstaller 打包脚本
└── tests/              # 单元测试（含 GeoServer mock）
```

## 9. 开发与测试

```bash
pip install -e ".[dev]"
pytest                        # 跑测试（内置 fake GeoServer，无需真实环境）
ruff check src tests          # 静态检查
```

## 10. 许可证

[MIT](./LICENSE)
