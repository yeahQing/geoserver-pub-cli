"""可选的 Web 可视化界面（FastAPI）。

仅当执行 `geopub serve` 时才会被导入，因此基础 CLI 不依赖 fastapi/uvicorn。
所有接口复用 core / client 的纯逻辑，返回 JSON 供前端渲染。
"""

import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import __version__, core
from .client import GeoServerClient
from .config import DbConfig, GeoConfig
from .excel_io import read_layer_names, read_style_mapping


def _resource_path(rel: str) -> Path:
    """兼容源码运行与 PyInstaller 单文件冻结两种场景。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / rel
    return Path(__file__).resolve().parent / rel


HTML_PATH = _resource_path("web/static/index.html")


# ---- 请求体模型 ----
class LayerPublishIn(BaseModel):
    mode: str = "file"  # file | all | list
    file_path: Optional[str] = None
    column: str = "图层名"
    tables: list[str] = []


class StylePublishIn(BaseModel):
    style_dir: str
    file_path: Optional[str] = None


class FetchIn(BaseModel):
    layers: list[str] = []
    file_path: Optional[str] = None
    column: str = "图层名"
    out: str = "sld_output"
    list_only: bool = False


class CheckIn(BaseModel):
    layers: list[str] = []
    file_path: Optional[str] = None
    column: str = "图层名"
    out: str = "layer_check_result.csv"
    deep: bool = False
    check_db: bool = False
    only_missing: bool = False
    with_store: bool = True
    with_style: bool = False


def make_app(geo: GeoConfig, db: DbConfig) -> FastAPI:
    app = FastAPI(title="GeoPub Web", version=__version__)

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        if HTML_PATH.exists():
            return HTMLResponse(HTML_PATH.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>index.html 未找到，请检查打包资源</h1>")

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "workspace": geo.workspace}

    @app.get("/api/config")
    def get_config() -> dict:
        return {
            "geoserver": {
                "url": geo.url,
                "user": geo.username,
                "workspace": geo.workspace,
                "password_set": bool(geo.password),
            },
            "database": {
                "host": db.host,
                "port": db.port,
                "dbname": db.dbname,
                "schema": db.schema,
                "user": db.user,
                "store": db.store,
            },
        }

    @app.post("/api/test")
    def test_conn() -> dict:
        with GeoServerClient(geo) as c:
            ok, info = c.check_connection()
        return {"reachable": ok, "detail": info}

    @app.get("/api/tables")
    def list_tables() -> dict:
        try:
            with GeoServerClient(geo) as c:
                tables = c.get_tables(db)
            return {"tables": tables}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc))

    def _resolve_layers(inp: FetchIn) -> list[str]:
        names: list[str] = list(inp.layers)
        if inp.file_path:
            names += read_layer_names(inp.file_path, inp.column)
        seen: set[str] = set()
        out: list[str] = []
        for n in names:
            if n and n not in seen:
                seen.add(n)
                out.append(n)
        return out

    @app.post("/api/layer/publish")
    def layer_publish(inp: LayerPublishIn) -> dict:
        try:
            with GeoServerClient(geo) as c:
                c.ensure_datastore(db)
                if inp.mode == "all":
                    tables = c.get_tables(db)
                elif inp.mode == "file":
                    if not inp.file_path:
                        raise HTTPException(status_code=400, detail="file 模式需提供文件路径")
                    tables = read_layer_names(inp.file_path, inp.column)
                else:
                    tables = inp.tables
                results = core.publish_layers(c, db, tables)
            return {"count": len(results), "results": results}
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/style/publish")
    def style_publish(inp: StylePublishIn) -> dict:
        mapping = read_style_mapping(inp.file_path) if inp.file_path else {}
        try:
            with GeoServerClient(geo) as c:
                results = core.publish_styles(c, inp.style_dir, mapping)
            return {"count": len(results), "results": results}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/fetch")
    def fetch(inp: FetchIn) -> dict:
        layers = _resolve_layers(inp)
        if not layers:
            raise HTTPException(status_code=400, detail="需提供 layers / file_path")
        try:
            with GeoServerClient(geo) as c:
                data = core.fetch_core(
                    c, layers, inp.out, report_path=None
                )
            return data
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/check")
    def check(inp: CheckIn) -> dict:
        names = _resolve_layers(inp)
        if not names:
            raise HTTPException(status_code=400, detail="需提供 layers / file_path")
        try:
            with GeoServerClient(geo) as c:
                data = core.check_layers(
                    c, names, db=db, deep=inp.deep, check_db=inp.check_db,
                    with_store=inp.with_store, with_style=inp.with_style,
                )
            if inp.only_missing:
                data = dict(data)
                data["records"] = [
                    r for r in data["records"] if not r["published"]
                ]
            from .check import build_header, write_csv

            rows = write_csv(
                inp.out, data, inp.with_store, inp.check_db, inp.with_style
            )
            data["csv"] = str(Path(inp.out).resolve())
            data["rows"] = rows
            data["columns"] = build_header(
                inp.with_store, inp.check_db, inp.with_style
            )
            return data
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc))

    return app
