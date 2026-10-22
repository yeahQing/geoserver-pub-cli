"""假 GeoServer：给 `geopub check` 端到端联调提供 REST 响应。

只用标准库，不引入真实依赖。支持的路径：
  GET /rest/workspaces/{ws}/layers.json          -> 工作空间图层全量
  GET /rest/workspaces/{ws}/layers/{name}         -> 单图层存在性（降级路径）
  GET /rest/workspaces/{ws}/datastores/{s}/featuretypes.json -> FeatureType 全量
  GET /rest/workspaces/{ws}                        -> 连通性
"""

import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

WS = "demo"
STORE = "pg_store"

LAYERS = {
    "poi_point": {"style": "poi_point", "store": STORE, "table": "poi_point"},
    "site_polygon": {"style": "line", "store": STORE, "table": "site_polygon"},
    "broken_layer": {"style": None, "store": STORE, "table": "broken_layer"},
    "no_style_layer": {"style": None, "store": "pg_store_alt", "table": "no_style_layer"},
}
FEATURETYPES = {"poi_point", "site_polygon", "broken_layer", "no_style_layer"}

# 开关：置 False 模拟清单端点 403，验证降级
LAYERS_ENDPOINT_OK = False


def _layer_entry(name, meta):
    entry = {"name": name}
    if meta["style"]:
        # 实测：该实例把 defaultStyle 序列化成 dict repr 字符串
        entry["defaultStyle"] = str({"name": f"{WS}:{meta['style']}"})
    # 实测：该实例把 resource 序列化成 dict repr 字符串
    entry["resource"] = str({
        "@type": "featureType",
        "name": f"{WS}:{meta['store']}.{meta['table']}",
    })
    entry["type"] = "table"
    return entry


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 静默
        pass

    def _send(self, code, body, ctype="application/json"):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        # 兼容 /geoserver 前缀（真实部署形如 http://host:8080/geoserver）
        if path.startswith("/geoserver"):
            path = path[len("/geoserver"):]

        if re.fullmatch(rf"/rest/workspaces/{WS}/layers\.json", path):
            if not LAYERS_ENDPOINT_OK:
                return self._send(403, {"error": "forbidden"})
            entries = [_layer_entry(n, m) for n, m in LAYERS.items()]
            return self._send(200, {"layers": {"layer": entries}})

        m = re.fullmatch(rf"/rest/workspaces/{WS}/layers/([^/.]+)", path)
        if m:
            name = m.group(1)
            if name in LAYERS:
                return self._send(200, {"layer": _layer_entry(name, LAYERS[name])})
            return self._send(404, {"error": "not found"})

        if re.fullmatch(
            rf"/rest/workspaces/{WS}/datastores/{STORE}/featuretypes\.json", path
        ):
            entries = [
                {"name": f"{STORE}:{n}"} for n in sorted(FEATURETYPES)
            ]
            return self._send(200, {"featureTypes": {"featureType": entries}})

        if path == f"/rest/workspaces/{WS}":
            return self._send(200, {"workspace": {"name": WS}})

        return self._send(404, {"error": "not found", "path": path})


if __name__ == "__main__":
    import sys

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18999
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()