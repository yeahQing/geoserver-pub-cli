# 跨平台打包指南（Windows / Linux / macOS）

本文档独立说明 `geopub` 在三大桌面平台上的**打包成单文件可执行程序**的方法与步骤。
命令用法、配置等见 `docs/USAGE.md`；本文仅关注"如何产出 `dist/geopub(.exe)`"。

---

## 0. 前置条件

- **Python ≥ 3.11**：用于解析 TOML 配置（`tomllib` 自 3.11 起内置）。
- **本机打包**需要 `pyinstaller`，它包含在 `build` extra 里（`pip install ".[web,build]"`）。
- 构建脚本固定为 `scripts/build.py`，三平台共用，已内置以下处理：
  - 强制把项目 `src/` 置顶 `PYTHONPATH`，**确保打包的是最新源码**（规避 editable 安装产生的旧副本陷阱）。
  - 每次用独立临时 `--workpath`，避免复用 PyInstaller 陈旧分析缓存。
  - 跨平台分隔符自适应（`;` / `:`），并把 Web 静态资源注入产物。
- 产物一律落在 `dist/<name>`（Windows 自动加 `.exe`）。
- **打包成功后自动复制到 `dist/`**（`windows` / `linux` / `macos` 子目录，存在才复制、不存在静默跳过——CI 环境无此目录不受影响），免手动拷贝；复制失败只告警、不影响构建产物。

> ⚠️ **核心约束**：PyInstaller **不能交叉编译**。无法在 Windows 上打出 Linux/macOS 包，反之亦然；每个平台的二进制必须在该平台上构建（或对应 CI runner 上构建）。

---

## 1. Windows 打包

### 方式一：venv + pip（常规，已装 Python 3.11）

```powershell
cd geoserver-pub-cli
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # PowerShell；CMD 用 .\.venv\Scripts\activate.bat
pip install --upgrade pip
pip install ".[web,build]"            # 装依赖 + pyinstaller
python scripts/build.py               # 产出 dist\geopub.exe
.\dist\geopub.exe --help              # 验证
```

> 若系统默认 `python` 不是 3.11，改用 `py -3.11 -m venv .venv` 等显式版本。

### 方式二：uv（推荐，免系统装 Python）

```powershell
winget install --id=astral-sh.uv -e   # 或到 https://astral.sh/uv 下载安装
cd geoserver-pub-cli
uv python install 3.11                # 自动下载 CPython 3.11
uv venv --python 3.11
uv pip install ".[web,build]"
uv run python scripts/build.py
.\dist\geopub.exe --help
```

### 产物与验证

- 产物：`dist/geopub.exe`（约 23 MB 单文件）。
- 验证：`.\dist\geopub.exe --help` 应打印子命令列表（`layer` / `style` / `fetch` / `serve`）。
- 直接运行示例：`.\dist\geopub.exe --config .\geopub.toml fetch --excel .\layer.xlsx --column "图层名"`。

### Windows 特有注意

- **SmartScreen 拦截**：未签名 exe 首次运行会被 SmartScreen 拦截，点"更多信息 → 仍要运行"即可；企业环境可代码签名消除。
- **密码特殊字符**：命令行含 `$ & * ( ?` 等，PowerShell 下用**单引号**包裹（逐字字符串），例如 `--password 'YOUR_PASSWORD'`。
- 路径含空格时加引号：`--excel "D:\My Docs\layer.xlsx"`。

---

## 2. Linux 打包

### 方式一：uv（推荐，CentOS 7 等老系统首选）

`uv` 自带 CPython 下载器，会在 CentOS 7 上自动拉起 3.11，**无需系统装 Python**；且在老 glibc（2.17）上构建的二进制兼容面最广（可运行于 CentOS 7 及所有更新的 Linux）。

```bash
# 安装 uv（CentOS 7 / 通用 Linux）
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"          # 让 uv 进入 PATH

cd /path/to/geoserver-pub-cli
uv python install 3.11                 # 自动下载 3.11（python-build-standalone）
uv venv --python 3.11
source .venv/bin/activate
uv pip install ".[web,build]"          # 装依赖 + pyinstaller
python scripts/build.py                # 产出 dist/geopub（Linux 单文件 ELF）
./dist/geopub --help
```

等价一行（全程 uv 驱动）：
```bash
cd geoserver-pub-cli && uv python install 3.11 && uv venv --python 3.11 && uv pip install ".[web,build]" && uv run python scripts/build.py && ./dist/geopub --help
```

### 方式二：venv + pip（常规，已装 Python 3.11）

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install ".[web,build]"
python scripts/build.py                # 产出 dist/geopub
```

### 产物与验证

- 产物：`dist/geopub`（无扩展名的 ELF 单文件）。
- 验证：`./dist/geopub --help`；首次运行若报权限不足：`chmod +x dist/geopub`。

### Linux 特有注意（兼容性，重要）

- **glibc 绑定**：产物**绑定构建机的 glibc 版本**。在 **CentOS 7（glibc 2.17）** 上构建的二进制，可运行于 CentOS 7 及所有更新的 Linux（Ubuntu / RHEL / Debian …）；反之在 **Ubuntu 上构建的则无法在 CentOS 7 跑**。
- **选老系统构建 = 最大兼容面**：目标机含老系统（如 CentOS 7），就在 CentOS 7（或其 WSL）上打包，而不是在 Ubuntu 上。
- 若目标机极老（glibc < 2.17），需换用更老的基础镜像构建，或改用 `manylinux` 方案（本工具未内置）。

---

## 3. macOS 打包

### 方式一：uv（推荐）

```bash
brew install uv                       # 或 curl -LsSf https://astral.sh/uv/install.sh | sh
cd /path/to/geoserver-pub-cli
uv python install 3.11
uv venv --python 3.11
source .venv/bin/activate
uv pip install ".[web,build]"
python scripts/build.py               # 产出 dist/geopub（macOS Mach-O 单文件）
./dist/geopub --help
```

### 方式二：venv + pip（常规，已装 Python 3.11）

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install ".[web,build]"
python scripts/build.py
```

### 产物与验证

- 产物：`dist/geopub`（Mach-O 单文件）。
- 验证：`./dist/geopub --help`；必要时 `chmod +x dist/geopub`。

### macOS 特有注意

- **架构（Apple Silicon vs Intel）**：GitHub 的 `macos-latest` 现已为 **Apple Silicon（arm64）**，CI 产出的二进制是 arm64。如需 **Intel（x86_64）** 版本，把 CI runner 改为 `macos-13`（Intel）。本机打包则跟随你当前 Mac 的架构。
- **Gatekeeper 拦截**：未签名单文件首次运行会被隔离，终端执行：
  ```bash
  xattr -d com.apple.quarantine ./dist/geopub   # 解除隔离后再运行
  ```
  或右键"打开"并确认。企业环境建议做开发者签名 + 公证以消除警告。

---

## 4. 自定义产物名

`scripts/build.py` 接受第一个参数为产物名（不带扩展名，Windows 自动补 `.exe`）：

```bash
python scripts/build.py geopub-pro     # 产出 dist/geopub-pro(.exe)
python scripts/build.py geopub-macos   # 三平台分别命名，便于归档区分
```

---

## 5. CI 自动构建（推荐用于三平台同时产出）

`.github/workflows/build.yml` 在以下时机触发：
- 推送 **`v*` 标签**（如 `git tag v1.0.0 && git push origin v1.0.0`）；
- 或 GitHub 网页手动 **`workflow_dispatch`**。

矩阵在 **ubuntu / windows / macos** 三个 runner 上各构建一份单文件程序，并作为 Artifact 上传。

```bash
# 本地打标签触发（示例）
git tag v1.0.0
git push origin v1.0.0
# → 到仓库 Actions 页面等待 build-binaries 完成 → 下载对应平台 Artifact
```

CI 关键步骤（与本地等价）：

```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.11" }
- run: pip install ".[web,build]"
- run: python scripts/build.py ${{ matrix.name }}   # 按矩阵命名
- uses: actions/upload-artifact@v4
  with: { name: ${{ matrix.name }}, path: dist/* }
```

> 本地**无需**配置 CI；只想拿包就打标签推送，去 Actions 下载即可。

---

## 6. 通用注意事项汇总

1. **不能交叉编译**：Windows / Linux / macOS 的二进制各自在对应平台构建（或对应 CI runner）。
2. **glibc 兼容性（仅 Linux）**：在更老 glibc 的系统上构建 = 更大兼容面；目标含老系统就选老系统构建。
3. **editable 安装旧副本陷阱**：若曾 `pip install -e .`，部分环境会把包复制进 `site-packages`，PyInstaller 可能打包旧代码。`scripts/build.py` 已强制 `PYTHONPATH=src` 规避；手动 `pyinstaller` 命令时请同样确保源码优先。
4. **平台激活脚本差异**：Windows PowerShell 用 `.\.venv\Scripts\Activate.ps1`，CMD 用 `activate.bat`；Linux/macOS 用 `source .venv/bin/activate`。
5. **未签名提示**：Windows SmartScreen、macOS Gatekeeper 均会对未签名单文件告警，属正常，按平台说明解除或做签名/公证。
6. **产物体积**：单文件约 20–30 MB（含 Python 运行时与依赖），属预期。
7. **Web 依赖可选**：`[web]` extra（fastapi/uvicorn）仅在需要 `geopub serve` 时安装；不装也能正常打包，仅 `serve` 子命令会提示缺失依赖。
