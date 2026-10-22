"""PyInstaller 打包入口（顶层脚本，不使用相对导入）。

`python -m geopub` 仍走 `src/geopub/__main__.py`；
打包时用本文件作为入口，避免相对导入在冻结环境中失效。
"""

from geopub.cli import app

if __name__ == "__main__":
    app()
