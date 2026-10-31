"""把 resources/icon.png 生成 resources/icon.icns（macOS 应用图标）。

icns 格式：'icns' + 总长度 + 若干块，每块 = 类型(4) + 块长(含头8字节) + PNG 数据。
现代 macOS 对 16~1024px 的块都接受 PNG 编码，无需 Mac 也能生成。

用法： py -3.13 mac/gen_icns.py
"""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "bytego_image_master" / "resources" / "icon.png"
DST = ROOT / "bytego_image_master" / "resources" / "icon.icns"

# (类型码, 目标像素)
SIZES = [
    ("icp4", 16),
    ("icp5", 32),
    ("icp6", 64),
    ("ic07", 128),
    ("ic08", 256),
    ("ic09", 512),
    ("ic10", 1024),  # 512x512@2x
    ("ic11", 32),    # 16x16@2x
    ("ic12", 64),    # 32x32@2x
    ("ic13", 256),   # 128x128@2x
    ("ic14", 512),   # 256x256@2x
]


def main() -> int:
    from PIL import Image

    img = Image.open(SRC).convert("RGBA")
    chunks = b""
    for code, size in SIZES:
        small = img.resize((size, size), Image.LANCZOS)
        buf = Path(f"_tmp_{size}.png")
        small.save(buf, format="PNG")
        data = buf.read_bytes()
        buf.unlink()
        chunks += code.encode("ascii") + struct.pack(">I", len(data) + 8) + data
        print(f"  {code} {size}px {len(data):,} bytes")
    blob = b"icns" + struct.pack(">I", len(chunks) + 8) + chunks
    DST.write_bytes(blob)
    print(f"写入 {DST}（{len(blob):,} bytes）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
