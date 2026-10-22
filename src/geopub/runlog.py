"""运行日志：每次操作自动追加到当前目录 geopub.log。

设计约束：
- 日志永远不影响主流程（写失败静默吞掉，绝不让日志把命令跑挂）；
- 控制台保持简洁，完整错误详情（含 GeoServer 原始响应体）写日志；
- 追加模式，UTF-8，运维用记事本 / vi 直接看；
- 位置固定为**启动命令时所在目录**（CWD），与配置文件自动探测的
  "当前目录" 约定一致。
"""

import datetime

LOG_FILENAME = "geopub.log"
_RAW_LIMIT = 4000  # 原始响应体记录上限，防止巨型 HTML 错误页刷爆日志


def _stamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    """追加一行带时间戳的日志。"""
    try:
        with open(LOG_FILENAME, "a", encoding="utf-8") as f:
            f.write(f"[{_stamp()}] {msg}\n")
    except OSError:
        pass


def log_block(title: str, body: str) -> None:
    """写多行块（如 GeoServer 原始响应体），超限时截断。"""
    if len(body) > _RAW_LIMIT:
        body = body[:_RAW_LIMIT] + f"\n...（已截断，完整共 {len(body)} 字符）"
    try:
        with open(LOG_FILENAME, "a", encoding="utf-8") as f:
            f.write(f"[{_stamp()}] {title}\n")
            for line in body.splitlines():
                f.write(f"    {line}\n")
    except OSError:
        pass


def log_separator() -> None:
    """分隔线，标记一次新运行的开始。"""
    try:
        with open(LOG_FILENAME, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 60 + "\n")
    except OSError:
        pass
