"""生成示例清单文件（.xlsx 版）。

对应配置项：
  [layer].file_path / [fetch].file_path / [check].file_path -> 图层名清单（单关键列）
  [style].file_path                                       -> 样式-图层映射（两列，一对多）

纯文本场景直接用同目录下的 layer_names.csv / style_mapping.csv 即可，
本脚本用于演示/生成 Excel 版本。

运行: python examples/generate_examples.py
"""

import os

from openpyxl import Workbook

HERE = os.path.dirname(os.path.abspath(__file__))


def build_layer_xlsx() -> None:
    """图层名清单：首行表头含「图层名」，其后每行一个图层名。

    空串与「无」会被程序跳过（这里各保留一行演示该行为）。
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "图层"
    ws.append(["图层名"])
    ws.append(["poi_point"])
    ws.append(["road_line"])
    ws.append(["cell_4g"])
    ws.append(["无"])  # 会被跳过
    ws.append([""])  # 空行会被跳过
    ws.append(["grid_5g"])
    out = os.path.join(HERE, "layer.xlsx")
    wb.save(out)
    print("wrote", out)


def build_style_mapping_xlsx() -> None:
    """样式-图层映射：首行表头被忽略，其后每行 列0=样式名（可带 .sld）、列1=图层名。

    同一样式跨多行即实现一对多映射。
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "样式映射"
    ws.append(["样式名", "图层名"])  # 表头，程序跳过
    ws.append(["poi_style", "poi_point"])
    ws.append(["road_style", "road_line"])
    ws.append(["cell_style.sld", "cell_4g"])  # 可带 .sld 后缀
    ws.append(["cell_style", "grid_5g"])  # 一对多：同名样式 → 多个图层
    ws.append(["grid_style", "grid_5g"])
    out = os.path.join(HERE, "style_mapping.xlsx")
    wb.save(out)
    print("wrote", out)


if __name__ == "__main__":
    build_layer_xlsx()
    build_style_mapping_xlsx()
    print("done")
