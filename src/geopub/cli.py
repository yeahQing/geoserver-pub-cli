"""命令行入口（typer）。

参数合并优先级：命令行显式值 > 配置文件(geopub.toml 等) > 默认值。
用 `geopub --config path.toml <subcommand> ...` 指定配置文件，或把
geopub.toml 放在当前目录 / 用户主目录自动加载。
"""

import os
import sys

import typer
from rich.console import Console

from . import commands
from . import check as check_mod
from . import fetch as fetch_mod
from . import __version__
from . import runlog
from .config import DbConfig, GeoConfig, load_config_file, pick
from .excel_io import read_layer_names

app = typer.Typer(
    help="GeoServer 批量图层发布与样式绑定工具（db / PostGIS 模式）",
    no_args_is_help=True,
)

console = Console()

# 全局配置（由 callback 在每次调用前加载）
CONFIG: dict = {}


def _version_callback(value: bool) -> None:
    """--version / -V 的回调：打印版本号后立即退出。"""
    if value:
        console.print(f"geopub {__version__}")
        raise typer.Exit()


_PWD_ARGS = {"--password", "--db-pass"}


def _sanitize_argv() -> list[str]:
    """返回脱敏后的命令行参数（密码值替换为 ***），用于启动日志。"""
    out: list[str] = []
    skip_next = False
    for i, a in enumerate(sys.argv):
        if skip_next:
            out.append("***")
            skip_next = False
            continue
        name, sep, _val = a.partition("=")
        if sep and name in _PWD_ARGS:
            out.append(f"{name}=***")
            continue
        out.append(a)
        if a in _PWD_ARGS and i + 1 < len(sys.argv):
            skip_next = True
    return out


@app.callback()
def main_callback(
    config: str = typer.Option(
        None, "--config", help="配置文件路径（.toml/.json/.yaml）；不传则自动探测"
    ),
    version: bool = typer.Option(
        False, "--version", "-V",
        callback=_version_callback,
        is_eager=True,
        help="显示版本号并退出",
    ),
) -> None:
    """加载配置文件到全局 CONFIG，并记录本次运行的启动日志。"""
    global CONFIG
    CONFIG = load_config_file(config)
    path = config or "(自动探测)"
    if CONFIG:
        console.print(f"[dim]已加载配置: {path}[/dim]")
    else:
        console.print(f"[dim]未找到配置文件，使用命令行/默认值: {path}[/dim]")
    # 启动日志：分隔线 + 脱敏后的完整命令行（密码绝不落盘）
    runlog.log_separator()
    runlog.log(f"geopub {__version__} 启动: {' '.join(_sanitize_argv())}")


def _geo(
    url: str | None,
    user: str | None,
    password: str | None,
    workspace: str | None,
) -> GeoConfig:
    url = pick(CONFIG, "geoserver", "url", url)
    user = pick(CONFIG, "geoserver", "user", user, "admin")
    password = pick(CONFIG, "geoserver", "password", password)
    workspace = pick(CONFIG, "geoserver", "workspace", workspace, "demo")
    if not url:
        console.print("[red]错误：未提供 GeoServer 地址（命令行 --url 或配置 [geoserver].url）[/red]")
        raise typer.Exit(code=1)
    if not password:
        console.print("[red]错误：未提供密码（命令行 --password 或配置 [geoserver].password）[/red]")
        raise typer.Exit(code=1)
    return GeoConfig(url=url, username=user, password=password, workspace=workspace)


def _db(
    host: str | None,
    port: int | None,
    dbname: str | None,
    schema: str | None,
    user: str | None,
    password: str | None,
    store: str | None,
) -> DbConfig:
    host = pick(CONFIG, "database", "host", host)
    port = pick(CONFIG, "database", "port", port, 5432)
    dbname = pick(CONFIG, "database", "dbname", dbname, "postgres")
    schema = pick(CONFIG, "database", "schema", schema, "public")
    user = pick(CONFIG, "database", "user", user, "postgres")
    password = pick(CONFIG, "database", "password", password)
    store = pick(CONFIG, "database", "store", store, "pg_store")
    if not host:
        console.print("[red]错误：未提供数据库 host（命令行 --db-host 或配置 [database].host）[/red]")
        raise typer.Exit(code=1)
    if not password:
        console.print("[red]错误：未提供数据库密码（命令行 --db-pass 或配置 [database].password）[/red]")
        raise typer.Exit(code=1)
    return DbConfig(
        host=host,
        port=int(port),
        dbname=dbname,
        schema=schema,
        user=user,
        password=password,
        store=store,
    )


@app.command("layer")
def layer_cmd(
    url: str | None = typer.Option(None, "--url"),
    user: str | None = typer.Option(None, "--user"),
    password: str | None = typer.Option(None, "--password"),
    workspace: str | None = typer.Option(None, "--workspace"),
    store: str | None = typer.Option(None, "--store", help="GeoServer 数据存储名"),
    db_host: str | None = typer.Option(None, "--db-host"),
    db_port: int | None = typer.Option(None, "--db-port"),
    db_name: str | None = typer.Option(None, "--db-name"),
    db_schema: str | None = typer.Option(None, "--db-schema"),
    db_user: str | None = typer.Option(None, "--db-user"),
    db_pass: str | None = typer.Option(None, "--db-pass"),
    file_path: str | None = typer.Option(None, "--file-path", "--excel", help="图层名清单文件路径（.xlsx 或 .csv，首行表头）"),
    column: str | None = typer.Option(None, "--column", help="清单/映射文件中图层名列标题"),
    all_tables: bool | None = typer.Option(None, "--all/--no-all", help="发布 schema 下所有表"),
    interactive: bool = typer.Option(False, "--interactive", help="交互勾选图层"),
) -> None:
    """发布 PostGIS 表为 GeoServer 图层。"""
    geo = _geo(url, user, password, workspace)
    db = _db(db_host, db_port, db_name, db_schema, db_user, db_pass, store)
    file_path = pick(CONFIG, "layer", "file_path", file_path)
    column = pick(CONFIG, "layer", "column", column, "图层名")
    all_tables = pick(CONFIG, "layer", "all", all_tables, False)
    commands.layer_publish(
        geo, db, file_path=file_path, column=column, all_tables=bool(all_tables),
        interactive=interactive,
    )


@app.command("style")
def style_cmd(
    url: str | None = typer.Option(None, "--url"),
    user: str | None = typer.Option(None, "--user"),
    password: str | None = typer.Option(None, "--password"),
    workspace: str | None = typer.Option(None, "--workspace"),
    style_dir: str | None = typer.Option(None, "--dir", help="SLD 文件目录"),
    file_path: str | None = typer.Option(None, "--file-path", "--excel", help="样式-图层映射文件（.xlsx 或 .csv，两列：样式名,图层名）"),
    interactive: bool = typer.Option(False, "--interactive", help="交互勾选样式"),
) -> None:
    """发布 SLD 样式并绑定为图层默认样式。"""
    geo = _geo(url, user, password, workspace)
    style_dir = pick(CONFIG, "style", "dir", style_dir)
    file_path = pick(CONFIG, "style", "file_path", file_path)
    if not style_dir:
        console.print("[red]错误：未提供 SLD 目录（命令行 --dir 或配置 [style].dir）[/red]")
        raise typer.Exit(code=1)
    commands.style_publish(geo, style_dir, file_path=file_path, interactive=interactive)


@app.command("fetch")
def fetch_cmd(
    url: str | None = typer.Option(None, "--url"),
    user: str | None = typer.Option(None, "--user"),
    password: str | None = typer.Option(None, "--password"),
    workspace: str | None = typer.Option(None, "--workspace"),
    layers: str | None = typer.Option(None, "--layers", help="逗号分隔的图层名列表"),
    file_path: str | None = typer.Option(None, "--file-path", "--excel", help="图层名清单文件路径（.xlsx 或 .csv，首行表头）"),
    column: str | None = typer.Option(None, "--column", help="清单/映射文件中图层名列标题"),
    out: str | None = typer.Option(None, "--out", help="SLD 输出目录"),
    report: str | None = typer.Option(None, "--report", help="汇总报告 JSON 路径"),
    list_only: bool = typer.Option(False, "--list", help="只列出将处理的图层，不下载"),
) -> None:
    """批量拉取图层默认样式的 SLD 到本地（只读，不改 GeoServer）。"""
    geo = _geo(url, user, password, workspace)
    file_path = pick(CONFIG, "fetch", "file_path", file_path)
    column = pick(CONFIG, "fetch", "column", column, "图层名")
    out = pick(CONFIG, "fetch", "out", out, "sld_output")
    report = pick(CONFIG, "fetch", "report", report)

    names: list[str] = []
    if layers:
        names += [x.strip() for x in layers.split(",") if x.strip()]
    if file_path:
        names += read_layer_names(file_path, column)

    seen: set[str] = set()
    layers_list: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            layers_list.append(n)

    if not layers_list and not list_only:
        console.print(
            "[red]错误：需通过 --layers / --file-path 提供图层清单[/red]"
        )
        raise typer.Exit(code=1)

    report_path = report or (None if list_only else os.path.join(out, "_sld_report.json"))
    fetch_mod.fetch_styles(geo, layers_list, out, report_path=report_path, list_only=list_only)


@app.command("check")
def check_cmd(
    url: str | None = typer.Option(None, "--url"),
    user: str | None = typer.Option(None, "--user"),
    password: str | None = typer.Option(None, "--password"),
    workspace: str | None = typer.Option(None, "--workspace"),
    layers: str | None = typer.Option(None, "--layers", help="逗号分隔的图层名列表"),
    file_path: str | None = typer.Option(None, "--file-path", "--excel", help="图层名清单文件路径（.xlsx 或 .csv，首行表头）"),
    column: str | None = typer.Option(None, "--column", help="清单文件中图层名列标题"),
    out: str | None = typer.Option(None, "--out", help="结果 CSV 输出路径"),
    deep: bool | None = typer.Option(None, "--deep/--no-deep", help="额外核对 FeatureType，识别 Layer 缺失的中间态"),
    check_db: bool | None = typer.Option(None, "--check-db/--no-check-db", help="额外核对数据库表是否存在（需 db 参数）"),
    only_missing: bool | None = typer.Option(None, "--only-missing/--no-only-missing", help="结果只输出未发布的图层"),
    with_store: bool | None = typer.Option(None, "--with-store/--no-store", help="输出图层所属数据存储（批量查，需 1+N 次请求）"),
    with_style: bool | None = typer.Option(None, "--with-style/--no-with-style", help="输出默认样式（逐图层查详情，较慢）"),
    db_host: str | None = typer.Option(None, "--db-host"),
    db_port: int | None = typer.Option(None, "--db-port"),
    db_name: str | None = typer.Option(None, "--db-name"),
    db_schema: str | None = typer.Option(None, "--db-schema"),
    db_user: str | None = typer.Option(None, "--db-user"),
    db_pass: str | None = typer.Option(None, "--db-pass"),
    db_store: str | None = typer.Option(None, "--db-store"),
) -> None:
    """按 CSV/清单核对图层是否已发布，结果输出到 CSV（只读，不改 GeoServer）。"""
    geo = _geo(url, user, password, workspace)
    file_path = pick(CONFIG, "check", "file_path", file_path)
    column = pick(CONFIG, "check", "column", column, "图层名")
    out = pick(CONFIG, "check", "out", out, "layer_check_result.csv")
    deep = bool(pick(CONFIG, "check", "deep", deep, False))
    check_db = bool(pick(CONFIG, "check", "check_db", check_db, False))
    only_missing = bool(pick(CONFIG, "check", "only_missing", only_missing, False))
    with_store = bool(pick(CONFIG, "check", "with_store", with_store, True))
    with_style = bool(pick(CONFIG, "check", "with_style", with_style, False))

    names: list[str] = []
    if layers:
        names += [x.strip() for x in layers.split(",") if x.strip()]
    if file_path:
        names += read_layer_names(file_path, column)

    seen: set[str] = set()
    layers_list: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            layers_list.append(n)

    if not layers_list:
        console.print("[red]错误：需通过 --layers / --file-path 提供图层清单[/red]")
        raise typer.Exit(code=1)

    # db 参数只在 --check-db 时才需要；未启用时不必强制填库连接
    db: DbConfig | None = None
    if check_db:
        db = _db(db_host, db_port, db_name, db_schema, db_user, db_pass, db_store)

    console.print(f"[cyan]待核对图层 {len(layers_list)} 个，结果将写入 {out}[/cyan]")
    check_mod.check_and_report(
        geo, layers_list, out, db=db, deep=deep, check_db=check_db,
        only_missing=only_missing, with_store=with_store, with_style=with_style,
    )


@app.command("serve")
def serve_cmd(
    url: str | None = typer.Option(None, "--url"),
    user: str | None = typer.Option(None, "--user"),
    password: str | None = typer.Option(None, "--password"),
    workspace: str | None = typer.Option(None, "--workspace"),
    db_host: str | None = typer.Option(None, "--db-host"),
    db_port: int | None = typer.Option(None, "--db-port"),
    db_name: str | None = typer.Option(None, "--db-name"),
    db_schema: str | None = typer.Option(None, "--db-schema"),
    db_user: str | None = typer.Option(None, "--db-user"),
    db_pass: str | None = typer.Option(None, "--db-pass"),
    db_store: str | None = typer.Option(None, "--db-store"),
    host: str = typer.Option("127.0.0.1", "--host", help="Web 监听地址"),
    port: int = typer.Option(8000, "--port", help="Web 监听端口"),
) -> None:
    """启动可选的 Web 可视化界面（需安装 fastapi/uvicorn）。"""
    geo = _geo(url, user, password, workspace)
    db = _db(db_host, db_port, db_name, db_schema, db_user, db_pass, db_store)
    try:
        from .web import make_app
        import uvicorn
    except ImportError as exc:
        console.print(
            f"[red]Web 界面依赖未安装，请执行: pip install \"geopub[web]\" ({exc})[/red]"
        )
        raise typer.Exit(code=1)

    app = make_app(geo, db)
    console.print(f"[green]GeoPub Web 已启动: http://{host}:{port}[/green]")
    console.print("[dim]按 Ctrl+C 停止[/dim]")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    app()
