"""批量拉取图层默认样式 SLD 到本地（只读，不改 GeoServer）。"""

from rich.console import Console

from . import core, runlog
from .client import GeoServerClient
from .config import GeoConfig

console = Console()


def fetch_styles(
    geo: GeoConfig,
    layers: list[str],
    out_dir: str,
    report_path: str | None = None,
    list_only: bool = False,
) -> None:
    """逐图层拉取默认样式 SLD 落盘到 out_dir，并写汇总报告（CLI 版，打印结果）。"""
    if list_only:
        for i, name in enumerate(layers, 1):
            console.print(f"  {i:>3}  {name}")
        return

    with GeoServerClient(geo) as client:
        data = core.fetch_core(client, layers, out_dir, report_path)
        for rec in data["records"]:
            if rec["status"] == "failed":
                runlog.log(f"[fetch] 失败 {rec['layer']}: {rec['detail']}")
            elif rec["status"] == "skipped":
                runlog.log(f"[fetch] 跳过 {rec['layer']}: {rec['detail']}")

    console.print("\n" + "=" * 50)
    console.print(f"完成: {len(data['records'])} 个图层")
    for k in ("ok", "skipped", "failed"):
        console.print(f"  {k}: {data['summary'].get(k, 0)}")
    console.print(f"SLD 目录: {out_dir}")
    runlog.log(
        f"[fetch] 完成: 共 {len(data['records'])}, "
        f"ok {data['summary'].get('ok', 0)} / "
        f"skipped {data['summary'].get('skipped', 0)} / "
        f"failed {data['summary'].get('failed', 0)}"
    )
    if report_path:
        console.print(f"详细报告: {report_path}")
