import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from bytego_image_master.ui.main_window import MainWindow, enable_dark_titlebar  # noqa: E402


def main() -> int:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("Bytego Image Master")
    app.setApplicationVersion("1.1.0")
    win = MainWindow()
    win.show()
    enable_dark_titlebar(win)
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
