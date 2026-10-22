"""核心业务逻辑：返回结构化结果，供 CLI 与 Web 复用。

与 commands.py / fetch.py 的区别：本模块只做业务逻辑并返回 dict / list，
不直接打印，便于 Web 接口以 JSON 形式返回。
"""

import os

import httpx

from .client import (
    GeoServerClient,
    _strip_ws,
    geoserver_error_detail,
    layer_failure_hint,
)
from .config import DbConfig


def check_layers(
    client: GeoServerClient,
    layers: list[str],
    db: DbConfig | None = None,
    deep: bool = False,
    check_db: bool = False,
    with_store: bool = True,
    with_style: bool = False,
) -> dict:
    """核对清单内每个图层的发布状态（只读，不写 GeoServer）。

    判定策略：优先一次 `list_layers()` 拉全量做集合比对（1 次请求）；
    该端点不可用（403/404/500）时自动降级为逐个 `exists_layer` 探测，
    保证任何环境下都能出结论。

    参数：
      - with_store: 批量查 FeatureType 填出所属 store（1 + N(store) 次请求，
        N 通常为个位数）。FeatureType 列表端点只带 name+href，但 **href
        里含 store 名**，因此不必逐图层拉详情就能填这一列。
      - with_style: 填默认样式。列表端点不含该信息，只能逐图层查详情
        （N 次请求），故**默认关闭**，按需开启。
      - db / check_db: 同时到 PostGIS 核对表是否存在，用于区分
        "库里有表只是没发布" 与 "库里根本没这张表"。
      - deep: 基于同一份 FeatureType 数据识别"FeatureType 在、Layer 缺"
        这一 GeoServer 删 Layer 不级联删 FeatureType 的中间态。

    返回 {"records": [...], "total": ..., "mode": ...}。
    每条 record：layer / published / detail / style / store / table。

    注意：deep / check_db / with_store 只是**附加**维度，不影响主判定方式。
    只要清单端点可用就仍走全量比对（1 次请求），不会退化成逐个探测。
    """
    records: list[dict] = []
    mode = "probe"
    catalog: set[str] = set()

    try:
        catalog = client.list_layers()
        mode = "catalog"
    except Exception:  # noqa: BLE001 —— 端点不可用时降级为逐个探测
        catalog = set()

    # store 与 FeatureType 判定共用同一份数据，只查一次
    featuretypes: dict[str, str] = {}
    if with_store or deep:
        try:
            featuretypes = client.list_featuretypes(db if deep else None)
        except Exception:  # noqa: BLE001
            featuretypes = {}

    db_tables: set[str] = set()
    if check_db and db is not None:
        try:
            db_tables = set(client.get_tables(db))
        except Exception:  # noqa: BLE001
            db_tables = set()

    for name in layers:
        rec: dict = {
            "layer": name,
            "published": False,
            "detail": "",
            "style": "",
            "store": "",
            "table": "",
        }
        bare = _strip_ws(name)
        if mode == "catalog":
            rec["published"] = bare in catalog
            rec["detail"] = "已发布" if rec["published"] else "未发布"
        else:
            # 探测路径必须用裸名：`exists_layer` 直接把名字拼进 URL，
            # 带 `workspace:` 前缀会 404，导致已发布图层被误判为未发布。
            try:
                rec["published"] = client.exists_layer(bare)
                rec["detail"] = "已发布" if rec["published"] else "未发布"
            except Exception as exc:  # noqa: BLE001
                rec["detail"] = f"检查失败: {type(exc).__name__}: {exc}"

        if rec["published"]:
            if with_store:
                rec["store"] = featuretypes.get(bare, "")
            if with_style:
                try:
                    rec["style"] = client.get_layer_style(bare)
                except Exception:  # noqa: BLE001
                    rec["style"] = ""

        # 附加维度：FeatureType 是否已存在（GeoServer 侧中间态）
        if deep:
            if rec["published"]:
                rec["featuretype"] = "是"
            else:
                rec["featuretype"] = "是" if bare in featuretypes else "否"

        # 附加维度：数据库表是否存在
        if check_db and db is not None:
            rec["table"] = "存在" if bare in db_tables else "不存在"

        records.append(rec)

    published = sum(1 for r in records if r["published"])
    data = {
        "mode": mode,
        "total": len(records),
        "published": published,
        "unpublished": len(records) - published,
        "catalog_size": len(catalog) if mode == "catalog" else None,
        "records": records,
    }

    # 未发布且库中也没表 → 直接给一句可执行的结论，避免再手工核对
    if check_db and db is not None:
        data["no_table"] = [
            r["layer"] for r in records if not r["published"] and r.get("table") == "不存在"
        ]
    if deep:
        data["featuretype_only"] = [
            r["layer"] for r in records
            if not r["published"] and r.get("featuretype") == "是"
        ]
    return data


def publish_layers(
    client: GeoServerClient, db: DbConfig, tables: list[str]
) -> list[dict]:
    """逐表发布 PostGIS 图层（幂等），返回每表结果。"""
    results: list[dict] = []
    for t in tables:
        if client.exists_layer(t):
            results.append({"layer": t, "status": "skipped", "detail": "已存在"})
            continue
        try:
            state = client.publish_db_layer(db, t)
        except httpx.HTTPStatusError as exc:
            detail = geoserver_error_detail(exc.response)
            hint = layer_failure_hint(detail, db)
            if hint:
                detail = f"{detail}\n    提示: {hint}"
            results.append(
                {
                    "layer": t,
                    "status": "failed",
                    "detail": detail,
                    "raw": exc.response.text or "",
                }
            )
            continue
        except Exception as exc:  # noqa: BLE001
            results.append(
                {"layer": t, "status": "failed", "detail": f"{type(exc).__name__}: {exc}"}
            )
            continue
        if state == "created":
            results.append({"layer": t, "status": "ok", "detail": "发布成功"})
        elif state == "recovered":
            results.append(
                {
                    "layer": t,
                    "status": "ok",
                    "detail": "已恢复：FeatureType 已存在，已重建图层",
                }
            )
        else:  # exists
            results.append({"layer": t, "status": "skipped", "detail": "已存在，跳过"})
    return results


def discover_sld_files(style_dir: str) -> list[str]:
    """递归收集目录下所有 .sld 文件（按路径排序）。"""
    files: list[str] = []
    for root, _dirs, fs in os.walk(style_dir):
        for f in fs:
            if f.lower().endswith(".sld"):
                files.append(os.path.join(root, f))
    return sorted(files)


def publish_styles(
    client: GeoServerClient,
    style_dir: str,
    mapping: dict[str, list[str]],
    sld_files: list[str] | None = None,
) -> list[dict]:
    """发布/更新 SLD 并绑定为图层默认样式，返回每样式结果。"""
    if sld_files is None:
        sld_files = discover_sld_files(style_dir)

    results: list[dict] = []
    for path in sld_files:
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path, "r", encoding="utf-8") as fh:
                sld = fh.read()
        except OSError as e:
            results.append(
                {"style": name, "publish": "failed", "detail": str(e), "binds": []}
            )
            continue

        try:
            if client.exists_style(name):
                client.update_style(name, sld)
                pub = "updated"
            else:
                client.publish_style(name, sld)
                pub = "created"
        except httpx.HTTPStatusError as exc:
            results.append(
                {
                    "style": name,
                    "publish": "failed",
                    "detail": geoserver_error_detail(exc.response)
                    + f"（SLD 大小 {len(sld)} 字节，请确认非空且为有效 SLD）",
                    "raw": exc.response.text or "",
                    "binds": [],
                }
            )
            continue
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "style": name,
                    "publish": "failed",
                    "detail": f"{type(exc).__name__}: {exc}",
                    "raw": "",
                    "binds": [],
                }
            )
            continue

        targets = mapping.get(name) or [name]
        binds: list[dict] = []
        for layer in targets:
            try:
                if not client.exists_layer(layer):
                    binds.append(
                        {
                            "layer": layer,
                            "status": "skipped",
                            "detail": "图层不存在，请先用 layer 命令发布该表后再绑定",
                        }
                    )
                    continue
                client.configure_default_style(layer, name)
                binds.append({"layer": layer, "status": "ok", "detail": "已绑定"})
            except httpx.HTTPStatusError as exc:
                binds.append(
                    {
                        "layer": layer,
                        "status": "failed",
                        "detail": geoserver_error_detail(exc.response),
                        "raw": exc.response.text or "",
                    }
                )
            except Exception as exc:  # noqa: BLE001
                binds.append(
                    {"layer": layer, "status": "failed", "detail": str(exc)}
                )
        results.append(
            {"style": name, "publish": pub, "targets": targets, "binds": binds}
        )
    return results


def fetch_core(
    client: GeoServerClient,
    layers: list[str],
    out_dir: str,
    report_path: str | None = None,
) -> dict:
    """逐图层拉取默认样式 SLD 落盘，返回汇总（含 records）。"""
    os.makedirs(out_dir, exist_ok=True)
    records: list[dict] = []
    for layer in layers:
        rec = {"layer": layer, "status": "failed", "style": None, "detail": ""}
        try:
            style_name, style_ws, reason = client.get_default_style(layer)
            if not style_name:
                rec.update(status="skipped", detail=reason)
                records.append(rec)
                continue

            sld_text = client.get_sld(style_name, style_ws)
            if not sld_text:
                rec.update(
                    status="failed",
                    style=style_name,
                    detail=f"取不到样式 SLD: {style_name}",
                )
                records.append(rec)
                continue

            out_file = os.path.join(out_dir, f"{layer}.sld")
            with open(out_file, "w", encoding="utf-8") as fh:
                fh.write(sld_text)
            rec.update(
                status="ok",
                style=style_name,
                detail=f"{len(sld_text)} bytes -> {os.path.basename(out_file)}",
            )
        except httpx.HTTPStatusError as exc:
            rec.update(detail=geoserver_error_detail(exc.response))
        except Exception as exc:  # noqa: BLE001
            rec.update(detail=f"{type(exc).__name__}: {exc}")
        records.append(rec)

    summary = {"ok": 0, "skipped": 0, "failed": 0}
    for r in records:
        summary[r["status"]] = summary.get(r["status"], 0) + 1

    data = {"summary": summary, "records": records}
    if report_path:
        import json

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return data
