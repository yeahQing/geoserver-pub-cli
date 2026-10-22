"""GeoServer 批量发布 CLI（db 模式）。

子命令：
  geopub layer  发布 PostGIS 表为 GeoServer 图层
  geopub style  发布 SLD 样式并绑定为图层默认样式
  geopub fetch  批量拉取图层默认样式 SLD（只读）
  geopub check  按清单核对图层发布状态，输出 CSV（只读）
"""

__version__ = "0.3.0"
