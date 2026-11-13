"""geopub style 发布链路的离线单元验证（不连真实 GeoServer）。

用假客户端替换 GeoServerClient，验证（对应 openspec 变更 add-style-only-upload）：
  1. 仅上传模式（styles_only=True）不触碰任何图层，binds/targets 恒为空
  2. exists_style 判定决定 created / updated 分支
  3. 默认模式保持：映射一对多绑定、无映射同名回退、图层缺失跳过
  4. 仅上传模式忽略传入的映射
  5. CLI 层 --styles-only 与 --file-path 互斥（在连接校验前失败）
  6. 配置合并：CLI 显式值 > 配置 [style].styles_only > 默认关闭

运行：pytest tests/test_style_publish.py（或 python tests/test_style_publish.py）
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from typer.testing import CliRunner

from geopub import cli as cli_mod
from geopub import commands, core
from geopub.config import GeoConfig, pick

SLD = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<StyledLayerDescriptor version="1.0.0" xmlns="http://www.opengis.net/sld">'
    "<NamedLayer><Name>n</Name></NamedLayer></StyledLayerDescriptor>"
)

GEO = GeoConfig(url="http://fake", username="u", password="p", workspace="demo")


class FakeStyleClient:
    """记录样式/图层方法调用；existing_* 决定存在性判定分支。"""

    def __init__(self, existing_styles=(), existing_layers=()):
        self.existing_styles = set(existing_styles)
        self.existing_layers = set(existing_layers)
        self.published = []  # (name, sld)
        self.updated = []  # (name, sld)
        self.bound = []  # (layer, style)
        self.layer_probes = []  # exists_layer 入参

    def exists_style(self, name):
        return name in self.existing_styles

    def publish_style(self, name, sld):
        self.published.append((name, sld))
        return True

    def update_style(self, name, sld):
        self.updated.append((name, sld))
        return True

    def exists_layer(self, layer):
        self.layer_probes.append(layer)
        return layer in self.existing_layers

    def configure_default_style(self, layer, style):
        self.bound.append((layer, style))
        return True


def make_sld_dir(tmp_path, names=("alpha", "beta")):
    for n in names:
        (tmp_path / f"{n}.sld").write_text(SLD, encoding="utf-8")
    return str(tmp_path)


# ---- 仅上传模式 ----

def test_styles_only_never_touches_layers(tmp_path):
    client = FakeStyleClient(existing_styles=("beta",), existing_layers=())
    sld_dir = make_sld_dir(tmp_path)
    results = core.publish_styles(client, sld_dir, {}, styles_only=True)

    assert client.layer_probes == [], "仅上传模式不得探测图层"
    assert client.bound == [], "仅上传模式不得绑定图层"
    by_name = {r["style"]: r for r in results}
    assert by_name["alpha"]["publish"] == "created"
    assert by_name["beta"]["publish"] == "updated"
    for r in results:
        assert r["targets"] == []
        assert r["binds"] == []
    assert [n for n, _ in client.published] == ["alpha"]
    assert [n for n, _ in client.updated] == ["beta"]


def test_styles_only_ignores_mapping(tmp_path):
    client = FakeStyleClient(existing_layers=("layer_x", "alpha"))
    sld_dir = make_sld_dir(tmp_path, names=("alpha",))
    results = core.publish_styles(
        client, sld_dir, {"alpha": ["layer_x", "alpha"]}, styles_only=True
    )
    assert client.layer_probes == []
    assert client.bound == []
    assert results[0]["targets"] == []
    assert results[0]["binds"] == []


# ---- 默认模式（行为保持） ----

def test_default_mode_mapping_and_fallback(tmp_path):
    client = FakeStyleClient(existing_layers=("layer_x", "beta"))
    sld_dir = make_sld_dir(tmp_path)
    results = core.publish_styles(client, sld_dir, {"alpha": ["layer_x"]})

    # alpha 按映射绑定 layer_x；beta 无映射按同名回退
    assert client.bound == [("layer_x", "alpha"), ("beta", "beta")]
    assert client.layer_probes == ["layer_x", "beta"]
    assert results[0]["binds"][0]["status"] == "ok"
    assert results[1]["binds"][0]["status"] == "ok"


def test_default_mode_missing_layer_skipped(tmp_path):
    client = FakeStyleClient(existing_layers=())
    sld_dir = make_sld_dir(tmp_path, names=("alpha",))
    results = core.publish_styles(client, sld_dir, {})

    assert client.bound == []
    bind = results[0]["binds"][0]
    assert bind["status"] == "skipped"
    assert "图层不存在" in bind["detail"]


# ---- CLI 互斥与配置合并 ----

runner = CliRunner()


def test_cli_styles_only_conflicts_with_mapping(monkeypatch):
    monkeypatch.setattr(cli_mod, "load_config_file", lambda explicit=None: {})
    result = runner.invoke(
        cli_mod.app, ["style", "--styles-only", "--file-path", "m.csv", "--dir", "x"]
    )
    assert result.exit_code == 1
    assert "互斥" in result.output


def test_cli_styles_only_passes_check_reaches_conn_validation(monkeypatch):
    """无映射时应通过互斥校验、到达连接参数校验（离线可判定）。"""
    monkeypatch.setattr(cli_mod, "load_config_file", lambda explicit=None: {})
    result = runner.invoke(cli_mod.app, ["style", "--styles-only", "--dir", "x"])
    assert result.exit_code == 1
    assert "互斥" not in result.output
    assert "GeoServer 地址" in result.output


def test_cli_config_styles_only_respects_no_flag(monkeypatch):
    """配置 styles_only=true 时，命令行 --no-styles-only 显式覆盖为关闭。"""
    cfg = {"style": {"styles_only": True, "file_path": "m.csv"}}
    monkeypatch.setattr(cli_mod, "load_config_file", lambda explicit=None: cfg)
    result = runner.invoke(
        cli_mod.app, ["style", "--no-styles-only", "--dir", "x"]
    )
    # 互斥校验只对开启仅上传模式生效；--no-styles-only 后不应触发互斥
    assert "互斥" not in result.output
    # file_path 来自配置文件，连接校验仍会触发（未给 --url）
    assert "GeoServer 地址" in result.output


def test_pick_styles_only_merge_semantics():
    cfg = {"style": {"styles_only": True}}
    assert bool(pick(cfg, "style", "styles_only", None, False)) is True
    assert bool(pick(cfg, "style", "styles_only", False, False)) is False
    assert bool(pick({}, "style", "styles_only", None, False)) is False


# ---- 仅上传模式的渲染汇总（commands 层） ----

def test_commands_styles_only_summary(monkeypatch, tmp_path, capsys):
    fake = FakeStyleClient(existing_styles=("beta",))
    sld_dir = make_sld_dir(tmp_path)

    class _FakeCtx:
        def __enter__(self):
            return fake

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(commands, "GeoServerClient", lambda geo: _FakeCtx())
    commands.style_publish(GEO, sld_dir, styles_only=True)
    out = capsys.readouterr().out
    assert "仅上传模式：不绑定图层" in out
    assert "发布样式: alpha" in out
    assert "更新样式: beta" in out
    assert "样式汇总：新增 1 / 更新 1" in out
    assert "->" not in out, "仅上传模式不得出现绑定结果行"
    assert "请先" not in out


def test_commands_styles_only_fail_report(monkeypatch, tmp_path, capsys):
    fake = FakeStyleClient()

    def _boom(name, sld):
        raise RuntimeError("boom")

    fake.publish_style = _boom
    sld_dir = make_sld_dir(tmp_path, names=("alpha",))

    class _FakeCtx:
        def __enter__(self):
            return fake

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(commands, "GeoServerClient", lambda geo: _FakeCtx())
    commands.style_publish(GEO, sld_dir, styles_only=True)
    out = capsys.readouterr().out
    assert "发布样式失败: alpha" in out
    assert "样式汇总：新增 0 / 更新 0 / 失败 1" in out


def test_commands_default_mode_summary_unchanged(monkeypatch, tmp_path, capsys):
    """默认模式的绑定汇总输出保持原有形态（回归保护）。"""
    fake = FakeStyleClient(existing_layers=("beta",))
    sld_dir = make_sld_dir(tmp_path)

    class _FakeCtx:
        def __enter__(self):
            return fake

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(commands, "GeoServerClient", lambda geo: _FakeCtx())
    commands.style_publish(GEO, sld_dir)
    out = capsys.readouterr().out
    assert "绑定 beta -> beta" in out
    # alpha 无映射按同名回退，但 alpha 图层不存在 → 跳过并提示（原有行为）
    assert "跳过绑定 alpha: 图层不存在" in out
    assert "绑定汇总：成功 1 / 跳过 1" in out
    assert "请先 `geopub layer`" in out


if __name__ == "__main__":
    import inspect

    mod = sys.modules[__name__]
    fns = [
        f for n, f in inspect.getmembers(mod, inspect.isfunction)
        if n.startswith("test_")
    ]
    for f in fns:
        f()
    print(f"\n{len(fns)} tests passed")
