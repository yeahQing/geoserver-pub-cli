# geopub 运维手册

**geopub** 是 GeoServer 批量图层发布与样式绑定工具（命令行，免安装 Python）。
本手册只讲怎么用，四个常用命令：`layer`（发布图层）、`style`（发布样式）、`fetch`（拉取样式）、`check`（核对发布状态）。

---

## 1. 部署包内容

| 文件 | 说明 |
|---|---|
| `windows/geopub.exe` | Windows 单文件程序，复制到任意目录即可用，无需安装 |
| `linux/geopub` | Linux 单文件程序（glibc ≥ 2.17，CentOS 7 及以上均可运行） |
| `geopub.example.toml` | 配置文件模板（复制改名 `geopub.toml` 后填写） |
| `layer_names.example.csv` | 图层名清单示例（发布图层 / 核对发布状态用） |
| `style_mapping.example.csv` | 样式-图层映射示例（绑定样式用） |
| `slds/` | 存放 SLD 样式文件的空目录 |

> 版本查看：`geopub.exe --version`（当前 0.3.0）。帮助：`geopub.exe --help`。
>
> 手册示例中的 `geopub.exe` 即 `windows\geopub.exe`；在**部署包根目录**执行命令时写 `windows\geopub.exe ...`，或先 `cd windows` 再执行。Linux 同理（`linux/geopub`）。

---

## 2. 第一次使用：写配置文件（推荐）

把 `geopub.example.toml` 复制一份、改名为 **`geopub.toml`**，和 `geopub.exe` 放同一目录，填好以下内容：

```toml
[geoserver]
url = "http://localhost:8080/geoserver"   # GeoServer 地址，必须带 /geoserver 后缀
user = "admin"
password = "真实密码"
workspace = "demo"   # 工作空间名

[database]
host = "localhost"
port = 5432
dbname = "gis"      # 待发布表所在的库
schema = "public"   # 待发布表所在的 schema
user = "postgres"
password = "真实密码"
store = "pg_store"   # GeoServer 数据存储名，不存在会自动创建
```

配置好后，命令行只需写少量参数，其余自动读取。

**注意（重要）**：
- 配置文件里的 Windows 路径用**正斜杠** `/`，不要用 `\`（如 `D:./data/layer.xlsx`）。
- 配置文件含明文密码，请妥善管理权限，不要外发。
- 工具启动时自动加载**当前目录**或**用户主目录**的 `geopub.toml`；也可用 `--config 路径` 显式指定。

---

## 3. 发布图层（layer）

把 PostGIS 里的表发布为 GeoServer 图层。

**方式一：按清单文件发布（推荐）**

先准备图层名清单（参照 `layer_names.example.csv`，Excel 或 CSV 均可）：

```
图层名
sample_supplies
sample_line
```

然后执行（在 `geopub.exe` 所在目录打开命令行）：

```powershell
geopub.exe layer --file-path layer_names.example.csv
```

**方式二：发布 schema 下全部表**

```powershell
geopub.exe layer --all
```

连接信息不写参数时自动读 `geopub.toml`；如需临时覆盖，可加 `--url`、`--workspace`、`--store`、`--db-schema` 等参数。

---

## 4. 发布样式并绑定（style）

把 `slds/` 目录下的 `.sld` 文件发布到 GeoServer 并绑定为图层默认样式。

**方式一：同名绑定（推荐，最简单）**

SLD 文件名与图层名一致时（如 `poi_point.sld` → 图层 `poi_point`），直接：

```powershell
geopub.exe style --dir .\slds
```

**方式二：按映射文件绑定（一个样式绑多个图层）**

准备映射文件（参照 `style_mapping.example.csv`，两列：样式名、图层名）：

```
样式名,图层名
road_style,highway
road_style,local_road
```

执行：

```powershell
geopub.exe style --dir .\slds --file-path style_mapping.example.csv
```

> 幂等：已存在的样式会被更新，不会重复创建；已存在的图层绑定会被刷新。

---

## 5. 拉取样式（fetch，只读安全）

把 GeoServer 上图层的默认样式 SLD 批量下载到本地（**只读，不改动服务器**），常用于备份。

```powershell
geopub.exe fetch --layers "poi_point,road_line" --out .\sld_backup
```

- `--layers`：逗号分隔的图层名；也可用 `--file-path 清单文件` 批量拉取。
- `--out`：输出目录，默认 `sld_output`，产出含汇总报告 `_sld_report.json`。
- 想先看看会处理哪些图层：加 `--list`（只列出不下载）。

---

## 6. 核对发布状态（check，只读安全）

发版前后核对清单里的图层**哪些已发布、哪些没发布**，结果输出 CSV。**只读，不改动服务器。**

```powershell
geopub.exe check --file-path layer_names.example.csv
```

终端输出示例：

```text
检查方式：全量清单比对（服务端共 11 个图层）
清单条目：4
  已发布：4
  未发布：0
结果 CSV：...\layer_check_result.csv（4 行）
```

结果 CSV（编码带 BOM，Excel 双击打开不乱码）：

```
序号,图层名,发布状态,数据存储,备注
1,sample_supplies,已发布,pg_store,已发布
2,sample_line,已发布,pg_store,已发布
3,not_published_yet,未发布,,未发布
```

**典型用法：出待发布清单**

```powershell
geopub.exe check --file-path layer_names.example.csv --only-missing --out todo_layers.csv
```

结果只含未发布的图层，可直接当 `layer` 命令的输入清单，形成"核对 → 发布 → 复核"闭环：

```powershell
geopub.exe layer --file-path todo_layers.csv
geopub.exe check --file-path todo_layers.csv
```

**常用开关**：

| 开关 | 作用 |
|---|---|
| `--only-missing` | 结果只输出未发布的图层 |
| `--check-db` | 追加「数据库表」列，连PostGIS 核对表是否存在，区分"库里有表没发布"与"库里没表" |
| `--deep` | 在备注中标出「FeatureType 已存在但 Layer 缺失」（重跑 `layer` 可自愈） |
| `--with-style` | 追加「默认样式」列（需逐图层查详情，清单长时较慢） |
| `--no-store` | 不输出「数据存储」列 |
| `--out` | 结果 CSV 路径，默认 `layer_check_result.csv` |

**说明**：
- 默认输出列为 `序号 / 图层名 / 发布状态 / 数据存储 / 备注`，**不会输出整列空白**；列随开关增减。
- 只有 `--check-db` 需要 `[database]` 配置；`--deep` 只连 GeoServer。
- 只读，可反复安全运行。

---

## 7. 常见问题

| 现象 | 原因与处理 |
|---|---|
| 发布图层报 400 "no table was found to extract the schema" | GeoServer 在 store 指向的库/schema 里找不到同名表。核对：① 表确实存在于该库该 schema；② 表名大小写完全一致；③ 清单与目标环境一致（dev/test/线上库内容可能不同） |
| 首次运行被 Windows 拦截（SmartScreen 蓝色弹窗） | 未签名程序属正常，点 **"更多信息 → 仍要运行"** |
| 认证失败 401 | 密码含特殊字符（如 `$ & * ( ?`），命令行里必须用**单引号**包裹：`--password 'YOUR_PASSWORD'`；写在 toml 配置里则不用转义 |
| 样式绑定 403 | 目标 Tomcat 的 `web.xml` 对 PUT/DELETE 做了全拒加固，需放开 PUT/DELETE 后重启 Tomcat |
| 连接超时 / 拒绝 | 检查 `url` 是否带 `/geoserver` 后缀、网络是否可达、数据库账号权限 |
| 找不到清单文件 | 相对路径按**命令行所在目录**解析，不是 exe 所在目录；建议用绝对路径 |
| Linux 提示权限不足 | `chmod +x geopub` 后再运行 |
| 控制台报错显示不全 / 窗口关了想回查 | 每次运行都会在**命令行所在目录**自动生成 `geopub.log`：完整命令行（密码已脱敏）、每条图层结果、失败项的 GeoServer 原始响应全文都在里面，用记事本打开即可 |
| `check` 的「默认样式」列是空的 | 该列默认不输出。GeoServer 图层**列表**接口只返回 name+href，样式只在**单图层详情**接口里，查它必须逐图层发请求。需要时加 `--with-style` |
| `check` 提示"逐个探测，已自动降级" | 该 GeoServer 关闭了图层列表接口权限（403/404/500），已自动改为逐个探测。结论一样，只是慢一些 |

---

## 8. 快速自检

部署到新机器后，按顺序执行确认环境正常：

```powershell
geopub.exe --version
geopub.exe --help
geopub.exe check --file-path layer_names.example.csv
geopub.exe fetch --list
```

四条都有正常输出（后两条会提示缺参数时读配置），说明程序可用。
