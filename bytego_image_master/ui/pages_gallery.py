import shutil
import time
from pathlib import Path

from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from .widgets import ImageDialog, Toast


class GalleryPage(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.ctrl = controller
        self.columns = 0
        self._build()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._rebuild)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        bar = QHBoxLayout()
        title = QLabel("作品库")
        title.setObjectName("sectionTitle")
        bar.addWidget(title)
        self.count_label = QLabel("")
        self.count_label.setObjectName("hint")
        bar.addWidget(self.count_label)
        bar.addStretch(1)
        self.open_dir_btn = QPushButton("打开输出目录")
        self.open_dir_btn.setObjectName("ghost")
        self.open_dir_btn.clicked.connect(self.ctrl.open_output_dir)
        bar.addWidget(self.open_dir_btn)
        refresh = QPushButton("刷新")
        refresh.setObjectName("ghost")
        refresh.clicked.connect(self.refresh)
        bar.addWidget(refresh)
        root.addLayout(bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.host = QWidget()
        self.grid = QGridLayout(self.host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.host)
        root.addWidget(self.scroll, 1)

        self.empty = QLabel("还没有作品，先生成一张吧")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setObjectName("hint")
        self.empty.setVisible(False)
        root.addWidget(self.empty)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._timer.start()

    def refresh(self):
        self._rebuild()

    def _rebuild(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        items = self.ctrl.history
        self.count_label.setText(f"共 {len(items)} 张")
        self.empty.setVisible(not items)
        if not items:
            return
        width = max(self.scroll.viewport().width(), 320)
        cols = max(1, width // 268)
        if cols == self.columns and self.grid.count():
            return
        self.columns = cols
        for idx, item in enumerate(items):
            card = self._make_card(item)
            self.grid.addWidget(card, idx // cols, idx % cols)

    def _make_card(self, item: dict) -> QFrame:
        path = item.get("path", "")
        card = QFrame()
        card.setObjectName("card")
        card.setFixedWidth(250)
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        thumb = QLabel()
        thumb.setFixedHeight(160)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setStyleSheet("background:#161B23;border-radius:10px;")
        pix = self.ctrl.pixmap_for(path, 226, 160)
        if not pix.isNull():
            thumb.setPixmap(pix)
        lay.addWidget(thumb)

        prompt = QLabel(item.get("prompt", "")[:120])
        prompt.setWordWrap(True)
        prompt.setToolTip(item.get("prompt", ""))
        prompt.setStyleSheet(f"color:{self.ctrl.COLORS['text_dim']};font-size:12px;")
        prompt.setMaximumHeight(48)
        lay.addWidget(prompt)

        meta = QLabel(f"{item.get('size', '')} · {item.get('quality', '')} · "
                      f"{time.strftime('%m-%d %H:%M', time.localtime(item.get('created', 0)))}")
        meta.setObjectName("hint")
        lay.addWidget(meta)

        row = QHBoxLayout()
        row.setSpacing(6)
        btn_open = QPushButton("查看")
        btn_open.setObjectName("ghost")
        btn_open.clicked.connect(lambda: ImageDialog(path, self).exec_())
        row.addWidget(btn_open)
        btn_copy = QPushButton("复制提示词")
        btn_copy.setObjectName("ghost")
        btn_copy.clicked.connect(lambda: self._copy(item.get("prompt", "")))
        row.addWidget(btn_copy)
        btn_del = QPushButton("删除")
        btn_del.setObjectName("ghost")
        btn_del.clicked.connect(lambda: self._delete(item))
        row.addWidget(btn_del)
        lay.addLayout(row)

        again = QPushButton("用这条提示词再生成")
        again.setObjectName("ghost")
        again.setCursor(Qt.PointingHandCursor)
        again.clicked.connect(lambda: self.ctrl.use_prompt(item.get("prompt", "")))
        lay.addWidget(again)
        return card

    def _copy(self, text: str):
        QGuiApplication.clipboard().setText(text)
        Toast(self, "提示词已复制", "ok")

    def _delete(self, item: dict):
        path = Path(item.get("path", ""))
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            Toast(self, f"删除失败：{exc}", "error")
            return
        self.ctrl.remove_history(item)
        Toast(self, "已删除", "ok")
