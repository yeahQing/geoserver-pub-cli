"""geopub check 的离线单元验证（不连真实 GeoServer/DB）。

用假客户端替换 GeoServerClient / psycopg2，验证：
  1. 全量清单模式下的已发布/未发布判定
  2. workspace: 前缀归一化不会误判
  3. 清单接口不可用时降级为逐个探测
  4. --deep 能识别「FeatureType 在、Layer 缺」
  5. --check-db 能区分「库里没表」
  6. CSV 输出内容与 utf-8-sig BOM
运行：python .scratch/check_unit_test.py
"""

import csv
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from geopub import check as check_mod
from geopub import core
from geopub.client import _resource_ref, _split_ref, _strip_ws, _style_name
from geopub.config import DbConfig

DB = DbConfig(host="h", dbname="d", schema="public", store="pg_store")

LAYER_NAMES = {"poi_point", "site_polygon", "no_style_layer"}
FEATURETYPES = {
    "poi_point": "pg_store",
    "site_polygon": "pg_store",
    "broken_layer": "pg_store",      # FeatureType 在、Layer 缺
    "no_style_layer": "pg_store_alt",
}
STYLES = {"poi_point": "poi_point", "site_polygon": "line"}


class FakeClient:
    """模拟一次全量清单返回；catalog_ok=False 时模拟端点不可用。"""

    def __init__(self, catalog_ok=True):
        self.catalog_ok = catalog_ok
        self.probe_calls = []

    def list_layers(self):
        if not self.catalog_ok:
            raise RuntimeError("403 Forbidden")
        return set(LAYER_NAMES)

    def exists_layer(self, name):
        self.probe_calls.append(name)
        return _strip_ws(name) in LAYER_NAMES

    def list_datastores(self):
        return ["pg_store", "pg_store_alt"]

    def list_featuretypes(self, db=None):
        return dict(FEATURETYPES)

    def get_layer_style(self, layer):
        return STYLES.get(_strip_ws(layer), "")

    def get_tables(self, db):
        return ["poi_point", "site_polygon", "no_style_layer"]


def show(title):
    print("\n" + "=" * 56)
    print(title)


def test_normalize():
    show("1. 名称归一化")
    assert _strip_ws("demo:poi_point") == "poi_point"
    assert _strip_ws("poi_point") == "poi_point"
    assert _strip_ws("  demo:a:b ") == "a:b", _strip_ws("  demo:a:b ")
    assert _split_ref("demo:pg_store.poi_point") == ("pg_store", "poi_point")
    assert _split_ref("poi_point") == ("", "poi_point")
    assert _split_ref(
        "http://gs/rest/workspaces/demo/layers/demo:pg_store.poi_point.json"
    ) == ("pg_store", "poi_point"), _split_ref(
        "http://gs/rest/workspaces/demo/layers/demo:pg_store.poi_point.json"
    )
    print("   OK")


def test_resource_repr():
    """回归：resource / defaultStyle 返回 dict repr 字符串时不能污染 store 列。"""
    show("1b. resource 为 dict repr 字符串（实测踩过的坑）")
    repr_str = "{'@type': 'featureType', 'name': 'demo:pg_store.poi_point'}"
    assert _resource_ref(repr_str) == "demo:pg_store.poi_point", _resource_ref(repr_str)
    assert _split_ref(_resource_ref(repr_str)) == ("pg_store", "poi_point")
    style_repr = "{'name': 'demo:line', 'workspace': {'name': 'demo'}}"
    assert _style_name(style_repr) == "line", _style_name(style_repr)
    # 正常形态不能被破坏
    assert _resource_ref({"name": "demo:pg_store.dw"}) == "demo:pg_store.dw"
    assert _style_name({"name": "demo:line"}) == "line"
    assert _resource_ref(None) == "" and _style_name(None) == ""
    # 非法的 repr 文本应原样返回而不是抛异常
    assert _resource_ref("{not a dict") == "{not a dict"
    print("   OK")


def test_catalog_mode():
    show("2. 全量清单模式判定")
    names = ["poi_point", "demo:site_polygon", "no_style_layer", "missing_one"]
    data = core.check_layers(FakeClient(), names)
    assert data["mode"] == "catalog", data["mode"]
    assert data["total"] == 4
    assert data["published"] == 3, data["published"]
    assert data["unpublished"] == 1
    got = {r["layer"]: r["published"] for r in data["records"]}
    assert got["demo:site_polygon"] is True, "带 workspace 前缀的清单项应判为已发布"
    assert got["missing_one"] is False
    st = {r["layer"]: r["style"] for r in data["records"]}
    assert st["demo:site_polygon"] == "", "默认样式默认不查，应为空"
    store = {r["layer"]: r["store"] for r in data["records"]}
    assert store["poi_point"] == "pg_store", store
    assert store["no_style_layer"] == "pg_store_alt", store
    print("   OK  mode=%s 已发布=%s 未发布=%s" % (
        data["mode"], data["published"], data["unpublished"]))


def test_probe_fallback():
    show("3. 清单端点不可用 -> 降级逐个探测")
    c = FakeClient(catalog_ok=False)
    data = core.check_layers(c, ["poi_point", "missing_one"])
    assert data["mode"] == "probe", data["mode"]
    assert data["published"] == 1 and data["unpublished"] == 1
    assert c.probe_calls == ["poi_point", "missing_one"], c.probe_calls
    # 回归：探测必须用裸名，带 workspace: 前缀会 404 误判为未发布
    c2 = FakeClient(catalog_ok=False)
    data2 = core.check_layers(c2, ["demo:poi_point", "demo:missing"])
    assert c2.probe_calls == ["poi_point", "missing"], c2.probe_calls
    assert data2["published"] == 1 and data2["unpublished"] == 1, data2
    print("   OK  mode=%s 逐个探测 %s / 前缀归一化 %s" % (
        data["mode"], c.probe_calls, c2.probe_calls))


def test_deep_and_db():
    show("4/5. deep + check-db 附加维度")
    names = ["poi_point", "demo:site_polygon", "broken_layer", "no_table_at_all"]
    data = core.check_layers(FakeClient(), names, db=DB, deep=True,
                             check_db=True, with_style=True)
    by = {r["layer"]: r for r in data["records"]}
    assert by["poi_point"]["style"] == "poi_point", by["poi_point"]
    assert by["demo:site_polygon"]["style"] == "line", by["demo:site_polygon"]
    assert by["poi_point"]["published"] and by["poi_point"]["featuretype"] == "是"
    assert by["broken_layer"]["published"] is False
    assert by["broken_layer"]["featuretype"] == "是"
    assert by["no_table_at_all"]["featuretype"] == "否"
    assert by["poi_point"]["table"] == "存在"
    assert by["no_table_at_all"]["table"] == "不存在"
    assert data["featuretype_only"] == ["broken_layer"], data["featuretype_only"]
    # 假库表清单里没有 broken_layer / no_table_at_all，两者都是"库里无表"
    assert data["no_table"] == ["broken_layer", "no_table_at_all"], data["no_table"]
    print("   OK  featuretype_only=%s no_table=%s" % (
        data["featuretype_only"], data["no_table"]))


def test_csv_output():
    show("6. CSV 输出")
    names = ["poi_point", "broken_layer", "no_table_at_all"]
    data = core.check_layers(FakeClient(), names, db=DB, deep=True, check_db=True)
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "sub", "res.csv")
        rows = check_mod.write_csv(out, data, check_db=True, with_style=True)
        assert rows == 3
        assert os.path.exists(out)
        raw = open(out, "rb").read(3)
        assert raw == b"\xef\xbb\xbf", "缺少 utf-8-sig BOM，Excel 会乱码: %r" % raw
        with open(out, encoding="utf-8-sig", newline="") as fh:
            got = list(csv.reader(fh))
    assert got[0] == ["序号", "图层名", "发布状态", "默认样式",
                      "数据存储", "数据库表", "备注"], got[0]
    assert len(got[1]) == len(got[0]), "每行列数须与表头一致"
    body = {r[1]: r for r in got[1:]}
    assert body["poi_point"][2] == "已发布"
    assert body["broken_layer"][2] == "未发布"
    # 备注优先级：库中无表（根因）> FeatureType 缺失（次要线索）
    assert "无此表" in body["broken_layer"][6], body["broken_layer"]
    assert "不存在" in body["broken_layer"], body["broken_layer"]
    assert "无此表" in body["no_table_at_all"][6], body["no_table_at_all"]
    for r in got[1:]:
        print("   ", r)

    # only_missing：只保留未发布行
    data2 = dict(data)
    data2["records"] = [r for r in data["records"] if not r["published"]]
    with tempfile.TemporaryDirectory() as d:
        out2 = os.path.join(d, "only.csv")
        n = check_mod.write_csv(out2, data2, check_db=True)
        assert n == 2, n
    print("   OK  only_missing 输出 %d 行" % n)


def test_dedup_and_empty():
    show("7. 重复项与空清单")
    names = ["poi_point", "poi_point", "missing_one"]
    data = core.check_layers(FakeClient(), names)
    assert data["total"] == 3, "去重应在 CLI 层完成，core 原样处理: %s" % data["total"]
    print("   OK  core 原样保留 %d 条（去重由 CLI 负责）" % data["total"])


if __name__ == "__main__":
    test_normalize()
    test_resource_repr()
    test_catalog_mode()
    test_probe_fallback()
    test_deep_and_db()
    test_csv_output()
    test_dedup_and_empty()
    print("\n全部通过")