"""业务命令：图层发布、样式发布与绑定（CLI 入口，负责打印）。"""

import os

import httpx
import typer
from rich.console import Console

from . import core, runlog
from .client import GeoServerClient, geoserver_error_detail
from .config import DbConfig, GeoConfig
from .excel_io import read_layer_names, read_style_mapping
from .interactive import choose_items

console = Console()


def layer_publish(
    geo: GeoConfig,
    db: DbConfig,
    file_path: str | None = None,
    column: str = "图层名",
    all_tables: bool = False,
    interactive: bool = False,
) -> None:
    """发布 PostGIS 表为 GeoServer 图层（幂等）。"""
    with GeoServerClient(geo) as client:
        try:
            client.ensure_datastore(db)
        except httpx.HTTPStatusError as exc:
            console.print(
                f"[red]数据存储创建/校验失败: {geoserver_error_detail(exc.response)}[/red]"
            )
            raise typer.Exit(code=1)

        if file_path:
            tables = read_layer_names(file_path, column)
            console.print(f"[cyan]从文件读取 {len(tables)} 个图层名[/cyan]")
        elif all_tables:
            tables = client.get_tables(db)
            console.print(f"[cyan]从数据库读取 {len(tables)} 张表[/cyan]")
        else:
            console.print("[red]错误：必须指定 --file-path 或 --all[/red]")
            raise typer.Exit(code=1)

        if interactive:
            tables = choose_items(tables, "选择要发布的图层")

        if not tables:
            console.print("[yellow]没有需要发布的图层[/yellow]")
            return

        results = core.publish_layers(client, db, tables)
        n_ok = n_skip = n_fail = 0
        for r in results:
            if r["status"] == "ok":
                n_ok += 1
                console.print(f"[green]发布成功: {r['layer']}[/green]")
                runlog.log(f"[layer] 成功 {r['layer']}: {r['detail']}")
            elif r["status"] == "skipped":
                n_skip += 1
                console.print(f"[yellow]跳过（已存在）: {r['layer']}[/yellow]")
                runlog.log(f"[layer] 跳过 {r['layer']}: {r['detail']}")
            else:
                n_fail += 1
                console.print(f"[red]发布失败: {r['layer']} ({r['detail']})[/red]")
                runlog.log(f"[layer] 失败 {r['layer']}: {r['detail']}")
                if r.get("raw"):
                    runlog.log_block(f"[layer] 失败 {r['layer']} - GeoServer 原始响应:", r["raw"])
        parts = [f"成功 {n_ok}"]
        if n_skip:
            parts.append(f"跳过 {n_skip}")
        if n_fail:
            parts.append(f"失败 {n_fail}")
        console.print(f"汇总：{' / '.join(parts)}")
        runlog.log(f"[layer] 汇总: {' / '.join(parts)}")
        if n_fail:
            console.print(
                "[yellow]失败详情与 GeoServer 原始响应已写入 geopub.log（当前目录）[/yellow]"
            )


def style_publish(
    geo: GeoConfig,
    style_dir: str,
    file_path: str | None = None,
    interactive: bool = False,
) -> None:
    """发布 SLD 样式并绑定为图层默认样式。"""
    mapping = read_style_mapping(file_path) if file_path else {}
    if file_path:
        console.print(f"[cyan]加载样式映射 {len(mapping)} 条[/cyan]")

    sld_files = core.discover_sld_files(style_dir)
    if not sld_files:
        console.print(f"[yellow]目录 {style_dir} 下未找到 .sld 文件[/yellow]")
        return

    if interactive:
        chosen = choose_items(
            [os.path.basename(f) for f in sld_files], "选择要发布的样式"
        )
        sld_files = [f for f in sld_files if os.path.basename(f) in chosen]

    with GeoServerClient(geo) as client:
        results = core.publish_styles(client, style_dir, mapping, sld_files)
        n_ok = n_skip = n_fail = n_pub_fail = 0
        for r in results:
            # 样式发布本身失败（如 GeoServer 数据目录写盘 500）：必须透出真因
            if r["publish"] == "failed":
                n_pub_fail += 1
                console.print(
                    f"[red]发布样式失败: {r['style']} ({r.get('detail', '')})[/red]"
                )
                runlog.log(f"[style] 发布失败 {r['style']}: {r.get('detail', '')}")
                if r.get("raw"):
                    runlog.log_block(
                        f"[style] 发布失败 {r['style']} - GeoServer 原始响应:", r["raw"]
                    )
                continue
            verb = "更新" if r["publish"] == "updated" else "发布"
            color = "cyan" if r["publish"] == "updated" else "green"
            console.print(f"[{color}]{verb}样式: {r['style']}[/]")
            runlog.log(f"[style] {verb} {r['style']}")
            for b in r["binds"]:
                if b["status"] == "ok":
                    n_ok += 1
                    console.print(f"[green]  绑定 {r['style']} -> {b['layer']}[/green]")
                    runlog.log(f"[style] 绑定 {r['style']} -> {b['layer']}")
                elif b["status"] == "skipped":
                    n_skip += 1
                    console.print(
                        f"[yellow]  跳过绑定 {b['layer']}: {b['detail']}[/yellow]"
                    )
                    runlog.log(f"[style] 跳过绑定 {b['layer']}: {b['detail']}")
                else:
                    n_fail += 1
                    console.print(
                        f"[red]  绑定失败 {b['layer']}: {b['detail']}[/red]"
                    )
                    runlog.log(f"[style] 绑定失败 {b['layer']}: {b['detail']}")
                    if b.get("raw"):
                        runlog.log_block(
                            f"[style] 绑定失败 {b['layer']} - GeoServer 原始响应:",
                            b["raw"],
                        )
        parts = [f"成功 {n_ok}"]
        if n_skip:
            parts.append(f"跳过 {n_skip}")
        if n_fail:
            parts.append(f"失败 {n_fail}")
        if n_pub_fail:
            parts.append(f"样式发布失败 {n_pub_fail}")
        if n_skip or n_fail or n_pub_fail:
            console.print(f"[yellow]绑定汇总：{' / '.join(parts)}[/yellow]")
        else:
            console.print(f"[green]绑定汇总：成功 {n_ok} 个[/green]")
        if n_pub_fail:
            console.print(
                "[red]有样式发布失败，请见上方 `发布样式失败: <样式名> (HTTP xxx: ...)` "
                "中的服务端原始报错。[/red]"
            )
            console.print(
                "[red]常见原因：① SLD 版本与媒体类型不匹配（No converter）；"
                "② GeoServer 数据目录写盘故障（Error persisting）；"
                "③ 样式被图层引用导致删除被拒（409）。可按具体报错针对性处理。[/red]"
            )
        if n_skip:
            console.print(
                "[yellow]提示：被跳过的图层在 GeoServer 中不存在，"
                "请先 `geopub layer` 发布该表，再重跑 `geopub style`。[/yellow]"
            )
