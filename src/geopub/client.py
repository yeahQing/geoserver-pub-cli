"""GeoServer REST 客户端封装（httpx + Basic Auth）。"""

import psycopg2
import re

import httpx

from .config import GeoConfig, DbConfig


def _html_text(fragment: str) -> str:
    """剥 HTML 标签并压缩空白，供错误页片段提取纯文本。"""
    txt = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", txt).strip()


def _tomcat_error_message(text: str) -> str | None:
    """从 Tomcat 错误页 HTML 中提取可读根因。

    GeoServer 未捕获异常经 Tomcat 渲染为 HTML 错误页，其结构为
    <p><b>Message</b> <u>根因一句话</u></p> / <p><b>Description</b> ...</p>。
    旧实现直接剥全部标签后取前 400 字符，页面样板（标题/Type/Status 行，
    约 350 字符）恰好把 Message 挤到截断边界，日志只剩半句（如
    "Trying to create new feature type inside the store, but no"）。
    这里改为按 <b>Message</b> 定点提取，拿不到再取 Description。
    """
    for label in ("Message", "Description"):
        m = re.search(
            rf"<b>\s*{label}\s*</b>\s*(.*?)</p>", text, re.S | re.I
        )
        if m:
            msg = _html_text(m.group(1))
            if msg:
                return msg
    return None


def geoserver_error_detail(r: "httpx.Response") -> str:
    """从 GeoServer 的错误响应中抽取可读信息，便于诊断 4xx/5xx。

    GeoServer 的报错通常藏在响应体里（XML 的 <ExceptionText> 或 JSON 的
    message 字段），httpx 的 raise_for_status 默认不打印，需主动提取。
    """
    try:
        status = r.status_code
        ct = r.headers.get("content-type", "")
        text = r.text or ""
        if "json" in ct:
            try:
                data = r.json()
                msg = (
                    data.get("message")
                    or data.get("error")
                    or data.get("ExceptionText")
                    or text
                )
                return f"HTTP {status}: {msg}"
            except Exception:
                pass
        m = re.search(r"<ExceptionText>(.*?)</ExceptionText>", text, re.S)
        if m:
            return f"HTTP {status}: {m.group(1).strip()}"
        # Tomcat 渲染的 HTML 错误页：定点提取 Message 根因，避免被页面样板挤掉
        tomcat = _tomcat_error_message(text)
        if tomcat:
            return f"HTTP {status}: {tomcat}"
        clean = _html_text(text)
        if not clean:
            return f"HTTP {status}"
        snippet = clean[:600]
        if len(clean) > 600:
            snippet += "…"
        return f"HTTP {status}: {snippet}"
    except Exception:
        return f"HTTP {r.status_code}"


# ---- SLD 版本探测与媒体类型 ----
# GeoServer REST 按上传请求的 Content-Type 选择 SLD 解析器：
#   SLD 1.0                                   -> application/vnd.ogc.sld+xml
#   SLD 1.1.0（GeoServer 2.x 样式编辑器默认） -> application/vnd.ogc.se+xml
# 版本与媒体类型不匹配时，服务端会报
#   "No converter for ... with preset Content-Type"
# 这类 500。因此上传前须按内容判断版本并选用对应媒体类型。
_SLD_CONTENT_TYPES = {
    "1.0": "application/vnd.ogc.sld+xml",
    "1.1.0": "application/vnd.ogc.se+xml",
}


def _detect_sld_version(sld: str) -> str:
    """根据根元素 version 属性判断 SLD 版本（默认 1.0）。"""
    head = sld[:4096]
    if re.search(r'version\s*=\s*["\']1\.1\.0["\']', head):
        return "1.1.0"
    return "1.0"


def _normalize_sld(sld: str) -> bytes:
    """去掉可能的 UTF-8 BOM，避免 XML 解析报 'Content is not allowed in prolog'。"""
    return sld.lstrip("\ufeff").encode("utf-8")


# ---- 引用名归一化 ----
# GeoServer REST 各版本返回的 name 形态不一致：图层列表里可能是裸名
# （"poi_point"），也可能是带工作空间前缀的（"demo:poi_point"）；FeatureType
# 则是 "store.table" 或 "workspace:store.table"。核对清单前统一剥掉
# 前缀，否则同一个图层会被误判为"未发布"。

def _strip_ws(name: str) -> str:
    """剥掉 `workspace:` 前缀，返回裸名；无前缀时原样返回。

    含 `://`（资源 URL）或 `/`（路径）时不做处理，避免把 "http" 当成
    工作空间名切错。
    """
    text = (name or "").strip()
    if "://" in text or "/" in text:
        return text
    if ":" in text:
        prefix, rest = text.split(":", 1)
        if rest.strip() and " " not in prefix:
            return rest.strip()
    return text


def _split_ref(ref: str) -> tuple[str, str]:
    """把 "workspace:store.table" / 资源 URL 拆成 (store, table)。

    处理顺序：去查询串 → 取路径末段 → 去 .json/.xml 后缀 → 剥工作空间
    前缀 → 按最后一个点拆 store/table。store 段里还带点时视为无法解析，
    返回 ("", 原文)。
    """
    text = (ref or "").strip()
    if not text:
        return "", ""
    text = text.rsplit("?", 1)[0].rstrip("/")   # 去查询串与尾斜杠
    text = text.rsplit("/", 1)[-1]              # 取路径末段
    for ext in (".json", ".xml"):               # 去 REST 资源后缀
        if text.lower().endswith(ext):
            text = text[: -len(ext)]
            break
    text = _strip_ws(text)
    if not text or "." not in text:
        return "", text
    head, tail = text.rsplit(".", 1)
    if head and "." not in head:
        return head, tail
    return "", text


def _style_name(default_style) -> str:
    """从 defaultStyle 字段取出样式裸名（兼容 dict / str / repr 字符串 / None）。"""
    if isinstance(default_style, dict):
        raw = default_style.get("name") or ""
    else:
        raw = _resource_ref(default_style)
    return _strip_ws(raw)


def _resource_ref(resource) -> str:
    """从图层的 `resource` 字段取出引用名（兼容 dict / str / None）。

    GeoServer 对 `resource` 的序列化并不稳定：多数版本返回 dict，但也有
    版本返回 **Python dict 的 repr 字符串**，形如
    `"{'@type': 'featureType', 'name': 'demo:pg_store.poi_point'}"`。
    若直接当路径切分，会把整段 dict 文本写进 store 列（实测踩过）。
    这里对疑似 repr 的字符串先尝试 ast.literal_eval 还原成 dict 再取 name。
    """
    if isinstance(resource, dict):
        return str(resource.get("name") or "")
    text = str(resource or "").strip()
    if not text:
        return ""
    if text.startswith("{"):
        try:
            import ast

            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return text
        if isinstance(parsed, dict):
            return str(parsed.get("name") or "")
    return text


class GeoServerClient:
    """对 GeoServer REST API 的薄封装。

    端点路径遵循 GeoServer 官方 REST 文档（/rest/...），不依赖任何第三方 SDK，
    便于对准不同版本的 GeoServer 实例逐个端点排查。
    """

    # check / 审计类只读操作共用的时间上限（单次 HTTP 请求）
    READ_TIMEOUT = 60.0

    def __init__(self, cfg: GeoConfig) -> None:
        self.cfg = cfg
        self.base = cfg.url.rstrip("/") + "/rest"
        self._client = httpx.Client(
            base_url=self.base,
            auth=(cfg.username, cfg.password),
            timeout=30.0,
        )

    # ---- 存在性检查 ----
    def exists_layer(self, layer: str) -> bool:
        r = self._client.get(f"/workspaces/{self.cfg.workspace}/layers/{layer}")
        if r.status_code == 200:
            return True
        if r.status_code == 404:
            return False
        r.raise_for_status()
        return False

    def exists_style(self, style: str) -> bool:
        """判断样式是否存在。

        注意：本 GeoServer 在 `GET /styles/{name}`（不带扩展名、无 Accept）
        时会触发 RestWrapperAdapter 序列化异常返回 HTTP 500
        ("No converter ... Content-Type 'null'")，导致简单的存在性检查
        直接 raise、整批样式发布在第一步就中断。因此这里统一用 `.json`
        端点 + Accept: application/json 探测（正常返回 200 / 404），并对
        5xx 保守地当作“已存在/已损坏”返回 True，交由后续更新逻辑用 PUT
        原地修复，而不是把流程中断。
        """
        r = self._client.get(
            f"/workspaces/{self.cfg.workspace}/styles/{style}.json",
            headers={"Accept": "application/json"},
        )
        if r.status_code == 200:
            return True
        if r.status_code == 404:
            return False
        # 5xx / 其他：保守视为存在（将被 PUT 修复），避免存在性检查中断整批
        return True

    # ---- 清单查询（只读，供 check / 审计使用）----
    # 实测（GeoServer 2.x，workspace=test）：`/layers.json` 列表端点只返回
    #   {"name": "...", "href": "...layers/{name}.json"}
    # 即**精简版**，不含 defaultStyle / resource；而单图层详情端点
    #   `/layers/{name}.json` 才带 defaultStyle 与 resource。
    # 因此列表只用于"是否已发布"的集合比对，样式与 store 另走
    # featuretypes / 详情端点批量取，避免为拿样式付出 N 次请求。

    def list_layers(self) -> set[str]:
        """列出工作空间下全部已发布图层的裸名集合（1 次请求）。

        仅用于 `geopub check` 的集合比对。返回的名称已剥掉 `workspace:`
        前缀，不同版本返回形态不一致（裸名 / 带前缀）都能对上。
        """
        r = self._client.get(
            f"/workspaces/{self.cfg.workspace}/layers.json",
            headers={"Accept": "application/json"},
            timeout=self.READ_TIMEOUT,
        )
        if r.status_code == 404:
            return set()
        r.raise_for_status()
        node = (r.json() or {}).get("layers") or {}
        items = node.get("layer") if isinstance(node, dict) else node
        if items is None:
            return set()
        if isinstance(items, (str, dict)):  # 单条时可能是对象而非数组
            items = [items]
        names: set[str] = set()
        for it in items:
            if not isinstance(it, dict):
                continue
            name = _strip_ws(str(it.get("name") or ""))
            if name:
                names.add(name)
        return names

    def list_datastores(self) -> list[str]:
        """列出工作空间下全部 datastore 名。"""
        r = self._client.get(
            f"/workspaces/{self.cfg.workspace}/datastores.json",
            headers={"Accept": "application/json"},
            timeout=self.READ_TIMEOUT,
        )
        if r.status_code == 404:
            return []
        r.raise_for_status()
        node = (r.json() or {}).get("dataStores") or {}
        items = node.get("dataStore") if isinstance(node, dict) else node
        if items is None:
            return []
        if isinstance(items, (str, dict)):
            items = [items]
        return [
            n for n in (_strip_ws(str(it.get("name") or "")) for it in items
                        if isinstance(it, dict)) if n
        ]

    def list_featuretypes(self, db: DbConfig | None = None) -> dict[str, str]:
        """列出 FeatureType，返回 {裸表名: store 名}。

        `db` 为空时遍历工作空间下**所有** datastore（1 + N 次请求，N 通常
        为个位数），这样既能填出每个图层的所属 store，又能让 `--deep`
        复用同一份数据判定"FeatureType 在、Layer 缺"；`db` 非空时只查
        指定 store（1 次请求）。

        列表端点的条目只带 `name` + `href`，store 名从 href 里提取：
        `.../datastores/{store}/featuretypes/{name}.json`。
        """
        stores = [db.store] if (db is not None and db.store) else self.list_datastores()
        out: dict[str, str] = {}
        for store in stores:
            r = self._client.get(
                f"/workspaces/{self.cfg.workspace}/datastores/"
                f"{store}/featuretypes.json",
                headers={"Accept": "application/json"},
                timeout=self.READ_TIMEOUT,
            )
            if r.status_code == 404:  # store 已被删除，跳过
                continue
            r.raise_for_status()
            node = (r.json() or {}).get("featureTypes") or {}
            items = node.get("featureType") if isinstance(node, dict) else node
            if items is None:
                continue
            if isinstance(items, (str, dict)):
                items = [items]
            for it in items:
                if not isinstance(it, dict):
                    continue
                raw = str(it.get("name") or "")
                if not raw:
                    continue
                name = _strip_ws(raw)
                # href 里的 store 更可信（name 字段有时不带 store 段）
                found = ""
                href = str(it.get("href") or "")
                m = re.search(r"/datastores/([^/]+)/featuretypes/", href)
                if m:
                    found = m.group(1)
                out[name] = found or store
        return out

    def get_layer_style(self, layer: str) -> str:
        """查单个图层的默认样式裸名（图层不存在或无样式时返回空串）。

        需逐图层调用（列表端点不含该信息），因此只在 `check --with-style`
        显式开启时才用。
        """
        r = self._client.get(
            f"/layers/{self.cfg.workspace}:{_strip_ws(layer)}.json",
            headers={"Accept": "application/json"},
            timeout=self.READ_TIMEOUT,
        )
        if r.status_code == 404:
            return ""
        r.raise_for_status()
        node = (r.json() or {}).get("layer") or {}
        return _style_name(node.get("defaultStyle"))

    # ---- 数据存储 ----
    def ensure_datastore(self, db: DbConfig) -> bool:
        """确保 datastore 存在；不存在则创建（开启 ExposePrimaryKeys）。"""
        r = self._client.get(f"/workspaces/{self.cfg.workspace}/datastores/{db.store}")
        if r.status_code == 200:
            return True
        body = {
            "dataStore": {
                "name": db.store,
                "connectionParameters": {
                    "entry": [
                        {"@key": "host", "$": db.host},
                        {"@key": "port", "$": str(db.port)},
                        {"@key": "database", "$": db.dbname},
                        {"@key": "schema", "$": db.schema},
                        {"@key": "user", "$": db.user},
                        {"@key": "passwd", "$": db.password},
                        {"@key": "dbtype", "$": "postgis"},
                        {"@key": "Expose primary keys", "$": "true"},
                    ]
                },
            }
        }
        r = self._client.post(f"/workspaces/{self.cfg.workspace}/datastores", json=body)
        r.raise_for_status()
        return True

    # ---- 图层发布 ----
    def publish_db_layer(self, db: DbConfig, table: str) -> str:
        """发布（或自愈）一个 PostGIS 表为 GeoServer 图层。

        返回状态字符串，供调用方生成友好结果：
          - "created"   : featuretype + layer 新建成功
          - "recovered" : featuretype 已存在、layer 缺失，已重建 layer（自愈）
          - "exists"    : 判定已存在（极少走到，exists_layer 通常已提前过滤）
        """
        body = {
            "featureType": {
                "name": table,
                "nativeName": table,
                "title": table,
                "srs": "EPSG:4326",
                "nativeCRS": "EPSG:4326",
            }
        }
        r = self._client.post(
            f"/workspaces/{self.cfg.workspace}/datastores/{db.store}/featuretypes",
            json=body,
        )
        if r.status_code in (200, 201):
            return "created"
        # 409 或 5xx 报 "already exists"：featuretype 已存在，转自愈（重建 Layer）
        if r.status_code == 409 or (
            r.status_code >= 400 and "already exists" in (r.text or "")
        ):
            self._recover_layer(db, table)
            return "recovered"
        r.raise_for_status()
        return "exists"

    def _recover_layer(self, db: DbConfig, table: str) -> None:
        """featuretype 已存在但 Layer 缺失时的自愈。

        直接 POST /workspaces/{ws}/layers 在本环境返回 405（Layer 是 featuretype
        的派生对象，GeoServer 不允许直接 POST 创建）。改为：删除旧 featuretype 后
        重新发布，连带重建 Layer。删 featuretype 仅移除 GeoServer 映射、不删 PostGIS 表。
        """
        if self.exists_layer(table):
            return
        base = (
            f"/workspaces/{self.cfg.workspace}"
            f"/datastores/{db.store}/featuretypes"
        )
        del_r = self._client.delete(f"{base}/{table}")
        if del_r.status_code not in (200, 201, 204, 404):
            del_r.raise_for_status()
        body = {
            "featureType": {
                "name": table,
                "nativeName": table,
                "title": table,
                "srs": "EPSG:4326",
                "nativeCRS": "EPSG:4326",
            }
        }
        post_r = self._client.post(base, json=body)
        if post_r.status_code in (200, 201):
            return
        post_r.raise_for_status()

    def get_tables(self, db: DbConfig) -> list[str]:
        """连接 PostGIS，列出指定 schema 下所有基表。"""
        dsn = (
            f"host={db.host} port={db.port} dbname={db.dbname} "
            f"user={db.user} password={db.password}"
        )
        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema=%s AND table_type='BASE TABLE' "
                    "ORDER BY table_name",
                    (db.schema,),
                )
                return [row[0] for row in cur.fetchall()]

    # ---- 样式发布 / 更新 / 绑定 ----
    def publish_style(self, style_name: str, sld_text: str) -> bool:
        body = _normalize_sld(sld_text)
        ct = _SLD_CONTENT_TYPES[_detect_sld_version(sld_text)]
        url = f"/workspaces/{self.cfg.workspace}/styles?name={style_name}"
        try:
            r = self._client.post(url, content=body, headers={"Content-Type": ct})
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            t = exc.response.text or ""
            # 版本探测失败时，用另一种 SLD 媒体类型重试一次
            if "converter" in t:
                alt = (
                    _SLD_CONTENT_TYPES["1.1.0"]
                    if ct == _SLD_CONTENT_TYPES["1.0"]
                    else _SLD_CONTENT_TYPES["1.0"]
                )
                r2 = self._client.post(
                    url, content=body, headers={"Content-Type": alt}
                )
                r2.raise_for_status()
                return True
            # 已存在（并发布路径走到这）：转更新（PUT 重写）
            if exc.response.status_code in (409, 500) and "already exists" in t:
                return self.update_style(style_name, sld_text)
            raise
        return True

    def update_style(self, style_name: str, sld_text: str) -> bool:
        """更新已存在样式的内容。

        采用 `PUT /styles/{name}?raw=true` 直接重写 SLD 资源，相比
        「DELETE + POST」更稳健：
          - 本环境 DELETE 样式会被 403 拒绝（"Can't delete style referenced
            by existing layers"，样式被图层/备用样式引用时禁止删除）；
          - PUT ?raw=true 不受引用限制，可直接覆盖 SLD 内容（已验证返回 200）。
        若服务端返回 404（样式确实不存在）则退化为 POST 新建。
        """
        ws = self.cfg.workspace
        body = _normalize_sld(sld_text)
        ct = _SLD_CONTENT_TYPES[_detect_sld_version(sld_text)]
        url = f"/workspaces/{ws}/styles/{style_name}?raw=true"
        try:
            r = self._client.put(url, content=body, headers={"Content-Type": ct})
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            t = exc.response.text or ""
            # 版本/媒体类型不匹配：换另一种 SLD 媒体类型重试一次
            if "converter" in t:
                alt = (
                    _SLD_CONTENT_TYPES["1.1.0"]
                    if ct == _SLD_CONTENT_TYPES["1.0"]
                    else _SLD_CONTENT_TYPES["1.0"]
                )
                r2 = self._client.put(
                    url, content=body, headers={"Content-Type": alt}
                )
                r2.raise_for_status()
                return True
            # 样式不存在：退化为新建
            if exc.response.status_code == 404:
                return self.publish_style(style_name, sld_text)
            raise
        return True

    def configure_default_style(self, layer: str, style_name: str) -> bool:
        """将某图层的默认样式设为 style_name。

        采用 GeoServer REST 标准惯用法：先 GET 完整 layer 表示，仅改
        defaultStyle 字段后再 PUT 回写。相比直接发局部 body，可避免偶发
        丢失 resource / geometry 关联（部分 GeoServer 版本对局部 PUT 较敏感）。
        """
        url = f"/workspaces/{self.cfg.workspace}/layers/{layer}"
        r = self._client.get(url, headers={"Accept": "application/json"})
        r.raise_for_status()
        data = r.json()
        data.setdefault("layer", {})["defaultStyle"] = {
            "name": style_name,
            "workspace": self.cfg.workspace,
        }
        r2 = self._client.put(url, json=data)
        r2.raise_for_status()
        return True

    # ---- 拉取（只读）----
    def get_default_style(self, layer: str) -> tuple[str | None, str | None, str]:
        """返回 (样式名, 样式工作空间名|None, 原因)。

        样式名为空时 reason 说明原因（图层不存在 / 无默认样式）。
        """
        r = self._client.get(
            f"/layers/{self.cfg.workspace}:{layer}.json",
            headers={"Accept": "application/json"},
        )
        if r.status_code == 404:
            return None, None, f"图层不存在(404) {self.cfg.workspace}:{layer}"
        r.raise_for_status()
        ds = r.json().get("layer", {}).get("defaultStyle")
        if not ds:
            return None, None, "无默认样式"
        name = ds.get("name") or ""
        if ":" in name:  # defaultStyle.name 常带 "workspace:" 前缀
            name = name.split(":", 1)[1]
        ws = ds.get("workspace")
        ws_name = ws.get("name") if isinstance(ws, dict) else ws
        return name, ws_name, ""

    def get_sld(self, style_name: str, style_ws: str | None = None) -> str | None:
        """按样式名取 SLD 文本；依次尝试 样式自带 ws → 当前 ws → 全局。
        """
        candidates: list[str] = []
        if style_ws:
            candidates.append(f"/workspaces/{style_ws}/styles/{style_name}")
        candidates.append(f"/workspaces/{self.cfg.workspace}/styles/{style_name}")
        candidates.append(f"/styles/{style_name}")
        for url in candidates:
            try:
                r = self._client.get(
                    url, headers={"Accept": "application/vnd.ogc.sld+xml"}
                )
            except httpx.TransportError:
                continue
            if r.status_code == 200 and "<" in r.text:
                return r.text
        return None

    def check_connection(self) -> tuple[bool, "str | int"]:
        """连通性探测：返回 (是否可达, 状态码或错误信息)。"""
        try:
            r = self._client.get(f"/workspaces/{self.cfg.workspace}")
            return (True, r.status_code)
        except Exception as exc:  # noqa: BLE001
            return (False, str(exc))

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GeoServerClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# ---- 发布失败的常见签名 → 人话提示（CLI 与 Web 共用） ----

def layer_failure_hint(detail: str, db: DbConfig | None = None) -> str:
    """按 GeoServer 报错签名给出可操作提示。

    目前覆盖图层发布 400 最常见的根因：数据存储在目标库/schema 里找不到
    同名表（"Trying to create new feature type inside the store, but no
    table was found to extract the schema from"）。提示带上库/schema/
    store 定位信息，运维可直接核对。
    """
    sig = detail.lower()
    if "no table was found" in sig or (
        "create new feature type" in sig and "but no" in sig
    ):
        where = ""
        if db is not None:
            where = f"（库 {db.dbname} / schema {db.schema} / store {db.store}）"
        return (
            "GeoServer 在数据存储指向的库/schema 中找不到同名表，无法提取表结构"
            + where
            + "。请核对：① 表确实存在于该库该 schema；② 表名大小写一致"
            "（含大写字母的表名需带双引号创建，存储名与清单名必须完全相同）；"
            "③ 清单与目标环境一致（dev/test/线上库内容可能不同）。"
        )
    return ""
