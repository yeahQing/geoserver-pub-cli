"""包入口，供 PyInstaller 打包为可执行文件。"""

from .cli import app

if __name__ == "__main__":
    app()
