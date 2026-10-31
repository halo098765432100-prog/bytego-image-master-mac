#!/usr/bin/env bash
# Bytego Image Master —— macOS 一键打包：.app + .dmg
#
# 在 Mac 上、项目根目录里执行：
#     bash mac/build_mac.sh
#
# 前提：
#   1. macOS 12+，终端能运行 python3（没有就先执行 xcode-select --install）
#   2. 联网（首次会下载 PyQt5 / PyInstaller）
#
# 产物：
#   dist/Bytego Image Master.app
#   dist/Bytego中转站GPT-Image-Grok Image Master-<版本>.dmg
#
# 说明：
#   - 安装包未做 Apple 公证，首次打开需右键 App →「打开」，或在
#     系统设置 → 隐私与安全性 里点「仍要打开」；
#     终端放行：xattr -cr "/Applications/Bytego Image Master.app"
#   - Apple Silicon 要求二进制至少有 ad-hoc 签名，脚本已自动执行
#     codesign -s -；以后如需正式分发，用 Developer ID 证书替换。
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PY:-python3}"
PIP_INDEX="${PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
echo "== 1/5 Python：$("$PY" --version 2>&1) =="
"$PY" -m venv .venv-mac
PYBIN=".venv-mac/bin/python"
"$PYBIN" -m pip install --upgrade pip -i "$PIP_INDEX" >/dev/null
echo "== 2/5 安装依赖（镜像：$PIP_INDEX）=="
"$PYBIN" -m pip install -i "$PIP_INDEX" -r requirements.txt "pyinstaller>=6.10"

echo "== 3/5 PyInstaller 构建 .app =="
"$PYBIN" -m PyInstaller --noconfirm --clean mac/BytegoImageMaster_mac.spec

APP="dist/Bytego Image Master.app"
[ -d "$APP" ] || { echo "错误：未找到 $APP"; exit 1; }

echo "== 4/5 ad-hoc 签名 =="
codesign --force --deep -s - "$APP" 2>/dev/null || echo "警告：ad-hoc 签名失败（本机运行通常仍可，继续）"

echo "== 5/5 生成 DMG =="
STAGE="mac/dmg_stage"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

VERSION=$("$PY" -c "import re,pathlib;print(re.search(r'VERSION\s*=\s*\"([^\"]+)\"',pathlib.Path('bytego_image_master/config.py').read_text(encoding='utf-8')).group(1))")
DMG="dist/Bytego中转站GPT-Image-Grok Image Master-${VERSION}.dmg"
hdiutil create -volname "Bytego Image Master" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"

echo ""
echo "完成：$DMG"
echo "   （同一目录还有 dist/Bytego Image Master.app 可直接运行）"
