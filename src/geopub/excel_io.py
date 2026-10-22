"""清单文件读取：支持 .xlsx（Excel）与 .csv（服务器易编辑文本）两种格式。

两种格式语义一致：首行为表头，其余为数据行。
- 图层名清单：指定列（默认「图层名」）逐行取值。
- 样式-图层映射：第 0 列样式名、第 1 列图层名，一对多（同一样式可多行）。

服务器场景推荐用 .csv：纯文本、vim/nano 直接编辑，且与 Excel 零成本互转。
"""

import csv
import os

from openpyxl import load_workbook


def _read_rows(path: str) -> tuple[tuple, list[tuple]]:
    """按扩展名读取表格式文件，返回 (表头元组, 数据行列表)。

    支持 .xlsx/.xls（openpyxl）与 .csv（标准库，utf-8/utf-8-sig）。
    .csv 用 utf-8-sig 读取，兼容 Excel 另存为 CSV 时写入的 BOM。
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = [tuple(r) for r in ws.iter_rows(values_only=True)]
    elif ext == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as fh:
            rows = [tuple(r) for r in csv.reader(fh)]
    else:
        raise ValueError(
            f"不支持的清单文件格式「{ext}」：仅支持 .xlsx / .xls / .csv"
        )
    if not rows:
        return (), []
    return tuple(rows[0]), list(rows[1:])


def read_layer_names(path: str, column: str) -> list[str]:
    """读取图层名清单（.xlsx 或 .csv）。

    首行为表头，按 `column` 定位列，逐行取值。
    跳过空串与值为 '无' 的行。
    """
    header, rows = _read_rows(path)
    if column not in header:
        raise ValueError(f"列 '{column}' 未在表头中找到：{list(header)}")
    idx = list(header).index(column)
    names: list[str] = []
    for row in rows:
        if idx >= len(row):
            continue
        val = row[idx]
        if val is None:
            continue
        text = str(val).strip()
        if text and text != "无":
            names.append(text)
    return names


def read_style_mapping(path: str) -> dict[str, list[str]]:
    """读取样式-图层映射（.xlsx 或 .csv，一对多）。

    首行为表头，忽略；其后每行：第 0 列样式名（可带 .sld 后缀），
    第 1 列图层名。同一样式可分多行对应多个图层。
    """
    _header, rows = _read_rows(path)
    mapping: dict[str, list[str]] = {}
    for row in rows:
        if not row or len(row) < 2:
            continue
        style, layer = row[0], row[1]
        if style is None or layer is None:
            continue
        s = str(style).strip()
        if s.lower().endswith(".sld"):
            s = s[:-4]
        mapping.setdefault(s, []).append(str(layer).strip())
    return mapping
