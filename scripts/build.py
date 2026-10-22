#!/usr/bin/env python3
"""跨平台打包脚本：将 geopub 打包为单文件可执行程序。

用法:
    python scripts/build.py                # 打包当前平台，产物名 geopub
    python scripts/build.py geopub-pro     # 指定产物名

产物位于 dist/<name>（Windows 为 .exe）。

说明:
- 强制把项目 src/ 置于 PYTHONPATH 最前，确保打包的是最新源码，
  避免环境中存在旧的可安装副本导致打包陈旧代码。
- 每次使用独立的临时 workpath，避免复用 PyInstaller 分析缓存（陈旧缓存会打包旧模块）。
- 打包前删除已存在的同名产物，避免覆盖被拦截。
前置依赖: pip install ".[build]"  (或 uv pip install ".[build]")
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "entrypoint.py"
STATIC = ROOT / "src" / "geopub" / "web" / "static"
# PyInstaller 跨平台分隔符：Windows 用 ; 其余用 :
SEP = ";" if sys.platform.startswith("win") else ":"


def _purge_stale_installed_copy() -> None:
    """卸载环境中可能残留的 geopub 安装副本，避免打包进旧代码。

    历史坑：曾用 `pip install .` 会在 site-packages 留下**非可编辑**副本，
    即便 build.py 已设置 PYTHONPATH=src，某些环境下 PyInstaller 仍可能取
    到这个旧副本（其 client.py 还是旧版 PUT，会触发 No converter）。
    构建前先卸载，使 src/ 成为唯一来源，打包结果必定新鲜。

    若未安装则静默忽略（uninstall 返回非 0 被 check=False 吞掉）。
    """
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", "geopub"],
            check=False,
            capture_output=True,
        )
    except Exception:  # noqa: BLE001
        pass



def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "geopub"
    if not ENTRY.exists():
        print(f"入口文件缺失: {ENTRY}", file=sys.stderr)
        return 1

    # 独立临时 workpath，避免复用陈旧分析缓存
    workpath = Path(tempfile.mkdtemp(prefix="geopub_build_"))
    data_arg = f"{STATIC}{SEP}web/static"

    # 删除已存在的同名产物，避免覆盖被拦截
    existing = ROOT / "dist" / (name + (".exe" if sys.platform.startswith("win") else ""))
    if existing.exists():
        try:
            existing.unlink()
        except OSError as exc:
            print(f"无法删除旧产物 {existing}: {exc}", file=sys.stderr)
            return 1

    # 构建前卸载可能残留的旧安装副本，确保只打包 src/ 最新源码
    _purge_stale_installed_copy()

    # 强制优先使用项目源码
    env = os.environ.copy()
    src = str(ROOT / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", name,
        "--onefile",
        "--noconfirm",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(workpath),
        "--add-data", data_arg,
        "--hidden-import", "geopub",
        "--hidden-import", "geopub.web",
        "--hidden-import", "fastapi",
        "--hidden-import", "uvicorn",
        "--hidden-import", "starlette",
        "--hidden-import", "pydantic",
        "--hidden-import", "openpyxl",
        "--hidden-import", "psycopg2",
        "--hidden-import", "httpx",
        "--hidden-import", "typer",
        "--hidden-import", "rich",
        "--hidden-import", "questionary",
        str(ENTRY),
    ]
    print("执行:", " ".join(cmd))
    rc = subprocess.call(cmd, env=env)
    if rc != 0:
        return rc

    print(f"构建完成: {existing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
