"""离屏渲染「开发者信息」弹窗并保存为 png，用于人工检查。

用法： py -3.13 tests/shot_dialog.py [输出png]
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from bytego_image_master.config import (APP_TITLE, DEVELOPER, DEVELOPER_QQ,  # noqa: E402
                                         VERSION, endpoint_label, endpoint_url)
from bytego_image_master.ui.widgets import DeveloperDialog  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "shot_dev.png"


def main():
    app = QApplication.instance() or QApplication([])
    dialog = DeveloperDialog(None, app_title=APP_TITLE, version=VERSION,
                             developer=DEVELOPER, qq=DEVELOPER_QQ,
                             endpoint_label=endpoint_label("cn"),
                             endpoint_url=endpoint_url("cn"))
    dialog.show()
    app.processEvents()
    pixmap = dialog.grab()
    pixmap.save(str(OUT))
    print(f"dialog -> {OUT} ({pixmap.width()}x{pixmap.height()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
