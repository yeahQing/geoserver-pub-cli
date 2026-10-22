"""连接配置模型与配置文件加载。"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python >= 3.11
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore


@dataclass
class GeoConfig:
    """GeoServer 连接配置（公共）。"""

    url: str
    username: str = "admin"
    password: str = ""
    workspace: str = "demo"


@dataclass
class DbConfig:
    """PostGIS 数据源配置（图层发布用）。"""

    host: str = ""
    port: int = 5432
    dbname: str = "postgres"
    schema: str = "public"
    user: str = "postgres"
    password: str = ""
    store: str = "pg_store"


# ---- 配置文件加载 ----
# 自动探测顺序：--config 显式路径 > 当前目录候选名 > 用户主目录 .geopub.toml
DEFAULT_CONFIG_NAMES = [
    "geopub.toml",
    "geopub.json",
    ".geopub.toml",
    "geopub.yaml",
    "geopub.yml",
]


def _load_raw(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".toml":
        if tomllib is None:
            raise RuntimeError("解析 TOML 需要 Python >= 3.11，或改用 .json 配置")
        return tomllib.loads(text)
    if suffix == ".json":
        return json.loads(text)
    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("解析 YAML 需安装 pyyaml: pip install pyyaml") from exc
        return yaml.safe_load(text) or {}
    raise RuntimeError(f"不支持的配置文件格式: {suffix}")


def resolve_config_path(explicit: str | None = None) -> Path | None:
    """返回要加载的配置文件路径；无则返回 None。"""
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise FileNotFoundError(f"配置文件不存在: {explicit}")
        return p
    for name in DEFAULT_CONFIG_NAMES:
        cand = Path.cwd() / name
        if cand.exists():
            return cand
    home = Path.home() / ".geopub.toml"
    if home.exists():
        return home
    return None


def load_config_file(explicit: str | None = None) -> dict:
    """加载配置文件为嵌套 dict；无文件返回空 dict。"""
    path = resolve_config_path(explicit)
    if path is None:
        return {}
    return _load_raw(path)


def section(cfg: dict, name: str) -> dict:
    return cfg.get(name, {}) or {}


def pick(cfg: dict, sec: str, key: str, cli: Any, default: Any = None) -> Any:
    """合并优先级：CLI 显式值 > 配置文件 > 默认值。

    cli 为 None（未显式传入）时才回退到配置/默认；布尔型选项需用
    `Optional[bool]` 且 `--x/--no-x` 形式以区分"未传"与"显式 False"。
    """
    if cli is not None:
        return cli
    return section(cfg, sec).get(key, default)
