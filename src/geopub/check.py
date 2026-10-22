"""按清单核对图层发布状态，输出 CSV（只读，不写 GeoServer）。

与 fetch.py 同构：核心判定在 core.check_layers，本模块只负责
CSV 落盘与终端呈现。

列按开关动态输出，避免出现一整列空白：
  - 默认        ：序号 / 图层名 / 发布状态 / 数据存储 / 备注
  - --check-db  ：追加「数据库表」
  - --with-style：追加「默认样式」（需逐图层查详情，较慢，故默认关闭）
  - --no-store  ：不输出「数据存储」
"""

import csv
import os

from rich.console import Console

from . import core, runlog
from .client import GeoServerClient
from .config import DbConfig, GeoConfig

console = Console()

# CSV 编码用 utf-8-sig（带 BOM），Excel 双击打开不乱码
ENCODING = "utf-8-sig"


def build_header(
    with_store: bool = True, check_db: bool = False, with_style: bool = False
) -> list[str]:
    """按开关拼出 CSV 表头（顺序必须与 build_row 一致）。"""
    cols = ["序号", "图层名", "发布状态"]
    if with_style:
        cols.append("默认样式")
    if with_store:
        cols.append("数据存储")
    if check_db:
        cols.append("数据库表")
    cols.append("备注")
    return cols


def _note_of(rec: dict) -> str:
    """已发布/未发布的可执行结论。

    未发布时的优先级：库中无表 > FeatureType 缺失。前者是根因（表不存在
    无法发布），比后者的"可自愈"线索更值得先看。
    """
    if rec["published"]:
        return "已发布"
    if rec.get("table") == "不存在":
        return "未发布（数据库中无此表，无法发布）"
    if rec.get("featuretype") == "是":
        return "未发布（FeatureType 已存在但 Layer 缺失，重跑 layer 可自愈）"
    return "未发布"


def build_row(
    i: int,
    rec: dict,
    with_store: bool = True,
    check_db: bool = False,
    with_style: bool = False,
) -> list:
    """拼出单行（顺序必须与 build_header 一致）。"""
    row = [i, rec["layer"], "已发布" if rec["published"] else "未发布"]
    if with_style:
        row.append(rec.get("style", ""))
    if with_store:
        row.append(rec.get("store", ""))
    if check_db:
        row.append(rec.get("table", ""))
    row.append(_note_of(rec))
    return row


def write_csv(
    path: str,
    data: dict,
    with_store: bool = True,
    check_db: bool = False,
    with_style: bool = False,
) -> int:
    """把核对结果写成 CSV，返回实际写出的行数。自动创建上级目录。"""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", newline="", encoding=ENCODING) as fh:
        writer = csv.writer(fh)
        writer.writerow(build_header(with_store, check_db, with_style))
        i = 0
        for rec in data["records"]:
            i += 1
            writer.writerow(build_row(i, rec, with_store, check_db, with_style))
    return i


def check_and_report(
    geo: GeoConfig,
    layers: list[str],
    out_csv: str,
    db: DbConfig | None = None,
    deep: bool = False,
    check_db: bool = False,
    only_missing: bool = False,
    with_store: bool = True,
    with_style: bool = False,
) -> dict:
    """核对 + 打印 + 落盘，返回 core.check_layers 的结果字典。"""
    with GeoServerClient(geo) as client:
        data = core.check_layers(
            client, layers, db=db, deep=deep, check_db=check_db,
            with_store=with_store, with_style=with_style,
        )

    if only_missing:
        data = dict(data)
        data["records"] = [r for r in data["records"] if not r["published"]]
        data["published"] = 0
        data["unpublished"] = len(data["records"])

    n = write_csv(out_csv, data, with_store, check_db, with_style)

    console.print(f"\n{'=' * 50}")
    if data["mode"] == "catalog":
        console.print(
            f"检查方式：全量清单比对（服务端共 {data['catalog_size']} 个图层）"
        )
    else:
        console.print("[yellow]检查方式：逐个探测（全量清单接口不可用，已自动降级）[/yellow]")
    console.print(f"清单条目：{data['total']}")
    console.print(f"  已发布：{data['published']}")
    console.print(f"  未发布：{data['unpublished']}")
    console.print(f"结果 CSV：{os.path.abspath(out_csv)}（{n} 行）")
    runlog.log(
        f"[check] 共 {data['total']}, 已发布 {data['published']}, "
        f"未发布 {data['unpublished']}, mode={data['mode']}, out={out_csv}"
    )

    missing = [r["layer"] for r in data["records"] if not r["published"]]
    if missing:
        preview = ", ".join(missing[:20])
        more = f" 等 {len(missing)} 个" if len(missing) > 20 else ""
        console.print(f"[yellow]未发布图层：{preview}{more}[/yellow]")
        console.print("[dim]提示：直接用这份 CSV 过滤出「未发布」行，即可作为 geopub layer 的输入清单[/dim]")

    for key, label, hint in (
        ("no_table", "数据库中无表", "这些图层无法发布，请先确认表是否存在于目标库/schema"),
        ("featuretype_only", "FeatureType 已存在但 Layer 缺失", "重跑 geopub layer 会自动重建 Layer（自愈）"),
    ):
        items = data.get(key) or []
        if items:
            console.print(f"[red]{label}（{len(items)}）：{', '.join(items[:20])}[/red]")
            console.print(f"[dim]  {hint}[/dim]")

    return data