import functools
import math
import os
import traceback
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen,
                         QPixmap, QRadialGradient)
from PyQt5.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QScrollArea, QSizePolicy, QToolButton, QVBoxLayout,
                             QWidget)

from ..theme import COLORS


def safe_slot(func):
    """槽函数兜底：后台异常只记录日志，不让 PyQt 直接 abort 整个进程。"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            traceback.print_exc()
            return None

    return wrapper


class Card(QFrame):
    def __init__(self, parent=None, flat=False):
        super().__init__(parent)
        self.setObjectName("cardFlat" if flat else "card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 16)
        self._layout.setSpacing(10)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget, stretch: int = 0) -> None:
        self._layout.addWidget(widget, stretch)

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)


class SectionTitle(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("sectionTitle")
        box.addWidget(self.title)
        self.sub = QLabel(subtitle)
        self.sub.setObjectName("hint")
        self.sub.setVisible(bool(subtitle))
        box.addWidget(self.sub)
        lay.addLayout(box)
        lay.addStretch(1)


class ChipButton(QPushButton):
    def __init__(self, text: str, checkable: bool = True, parent=None):
        super().__init__(text, parent)
        self.setObjectName("chip")
        self.setCheckable(checkable)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)


class NavButton(QToolButton):
    def __init__(self, text: str, icon_text: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("nav")
        self.setText(text)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.setMinimumHeight(38)
        if icon_text:
            self.setIconText(icon_text)


class Toast(QFrame):
    def __init__(self, parent, text: str, kind: str = "info"):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        colors = {
            "info": (COLORS["surface2"], COLORS["border_light"], COLORS["text"]),
            "ok": ("#12291F", "#1F5C43", COLORS["ok"]),
            "error": (COLORS["danger_soft"], "#5A2A33", COLORS["danger"]),
            "warn": ("#2C2313", "#5C4A1F", COLORS["warn"]),
        }
        bg, border, fg = colors.get(kind, colors["info"])
        self.setStyleSheet(
            f"QFrame{{background:{bg};border:1px solid {border};border-radius:10px;}}"
            f"QLabel{{color:{fg};font-size:12px;}}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 9, 14, 9)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(420)
        lay.addWidget(self.label)
        self.adjustSize()
        self._place()
        self.show()
        self.raise_()
        QTimer.singleShot(3200, self._dismiss)

    def _place(self) -> None:
        parent = self.parentWidget()
        if not parent:
            return
        x = parent.width() - self.width() - 26
        y = parent.height() - self.height() - 26
        self.move(max(12, x), max(12, y))

    def _dismiss(self) -> None:
        self.close()
        self.deleteLater()


class ImageCanvas(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None, min_height: int = 260):
        super().__init__(parent)
        self._pixmap: QPixmap = QPixmap()
        self._path = ""
        self._loading = False
        self._loading_text = "正在生成…"
        self._hints: list[str] = []
        self._hint_index = 0
        self._offset = 0
        self._angle = 0.0
        self._pulse = 0.0
        self._flash = 0.0
        self._timer: QTimer | None = None
        self.setMinimumHeight(min_height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)

    def set_image(self, path: str) -> bool:
        if not path or not os.path.exists(path):
            self._pixmap = QPixmap()
            self._path = ""
            self.update()
            return False
        pix = QPixmap(path)
        if pix.isNull():
            self._pixmap = QPixmap()
            self._path = ""
            self.update()
            return False
        self._pixmap = pix
        self._path = path
        self.update()
        return True

    def clear_image(self) -> None:
        self._pixmap = QPixmap()
        self._path = ""
        self.update()

    def path(self) -> str:
        return self._path

    # ------------------------------------------------------------- loading
    def set_loading(self, loading: bool, text: str = "正在生成…",
                    hints: Optional[list[str]] = None) -> None:
        """生成中的动态占位：有图时不做任何叠加。"""
        self._loading = bool(loading)
        self._loading_text = text
        self._hints = list(hints or [])
        self._hint_index = 0
        if loading:
            if self._timer is None:
                self._timer = QTimer(self)
                self._timer.timeout.connect(self._advance)
            if not self._timer.isActive():
                self._timer.start(50)
        elif self._timer is not None:
            self._timer.stop()
        self.update()

    def is_loading(self) -> bool:
        return self._loading

    def flash(self) -> None:
        """出图瞬间闪一下白光，强化"完成"的感知。"""
        self._flash = 1.0
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._advance)
        if not self._timer.isActive():
            self._timer.start(50)
        self.update()

    def _advance(self) -> None:
        self._offset = (self._offset + 16) % 1000
        self._angle = (self._angle + 7) % 360
        self._pulse = (self._pulse + 0.045) % 6.2831853
        if self._flash > 0:
            self._flash = max(0.0, self._flash - 0.035)
        if self._loading and self._hints:
            self._hint_index = (self._hint_index + 1) % len(self._hints)
        self.update()

    def _paint_loading(self, painter: QPainter, rect: QRect) -> None:
        accent = QColor(COLORS["accent"])

        # 斜向扫光
        band = 260
        span = rect.width() + band
        pos = self._offset % span
        grad = QLinearGradient(pos - band, 0, pos, 0)
        grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad.setColorAt(0.5, QColor(76, 141, 255, 34))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(rect, grad)

        cx = rect.width() / 2
        cy = rect.height() / 2 - 12

        # 中心光晕
        glow = QRadialGradient(cx, cy, 150)
        glow.setColorAt(0.0, QColor(76, 141, 255, 46))
        glow.setColorAt(0.55, QColor(76, 141, 255, 14))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QRect(int(cx - 150), int(cy - 150), 300, 300))

        # 旋转弧 + 呼吸外圈
        radius = 30 + 2 * float(math.sin(self._pulse))
        painter.setBrush(Qt.NoBrush)
        pen = QPen(QColor(76, 141, 255, 60))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawEllipse(QRect(int(cx - radius), int(cy - radius),
                                  int(radius * 2), int(radius * 2)))
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._angle)
        pen = QPen(accent)
        pen.setWidth(3)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(QRect(int(-radius), int(-radius), int(radius * 2), int(radius * 2)),
                        0, 100 * 16)
        painter.restore()

        # 主文案 + 轮播小文案
        painter.setPen(QPen(QColor(COLORS["text"])))
        painter.setFont(QFont("Microsoft YaHei UI", 12))
        main_rect = QRect(int(cx - 200), int(cy + 48), 400, 28)
        painter.drawText(main_rect, Qt.AlignCenter, self._loading_text)
        if self._hints:
            painter.setPen(QPen(QColor(COLORS["text_mute"])))
            painter.setFont(QFont("Microsoft YaHei UI", 10))
            hint_rect = QRect(int(cx - 200), int(cy + 74), 400, 22)
            painter.drawText(hint_rect, Qt.AlignCenter, self._hints[self._hint_index])

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        painter.fillRect(rect, QColor(COLORS["surface2"]))
        tile = 14
        light = QColor("#1A202A")
        dark = QColor("#161B23")
        painter.setPen(Qt.NoPen)
        y = 0
        row = 0
        while y < rect.height():
            x = 0
            col = 0
            while x < rect.width():
                painter.setBrush(light if (row + col) % 2 == 0 else dark)
                painter.drawRect(QRect(x, y, tile, tile))
                x += tile
                col += 1
            y += tile
            row += 1

        if self._loading and self._pixmap.isNull():
            self._paint_loading(painter, rect)
            return

        if self._pixmap.isNull():
            painter.setPen(QPen(QColor(COLORS["text_mute"])))
            painter.setFont(QFont("Microsoft YaHei UI", 11))
            painter.drawText(rect, Qt.AlignCenter, "输入提示词后按 Ctrl+Enter 开始生成")
            return
        scaled = self._pixmap.size().scaled(self.size(), Qt.KeepAspectRatio)
        target = QRect(0, 0, scaled.width(), scaled.height())
        target.moveCenter(rect.center())
        painter.drawPixmap(target, self._pixmap)

        if self._flash > 0:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, int(70 * self._flash)))
            painter.drawRect(target)

    def mouseReleaseEvent(self, event):
        if not self._pixmap.isNull() and event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class StageStepper(QWidget):
    """生成阶段指示：准备 → 连接 → 绘制 → 保存 → 完成。"""

    STAGES = ["准备", "连接", "绘制", "保存", "完成"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stage = -1
        self._pulse = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        self.setFixedHeight(44)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _tick(self) -> None:
        self._pulse = (self._pulse + 0.07) % 6.2831853
        self.update()

    def set_stage(self, index: int) -> None:
        index = max(-1, min(index, len(self.STAGES) - 1))
        if index == self._stage:
            return
        self._stage = index
        if index >= 0 and not self._timer.isActive():
            self._timer.start()
        elif index < 0:
            self._timer.stop()
        self.update()

    def stage(self) -> int:
        return self._stage

    def reset(self) -> None:
        self.set_stage(-1)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        n = len(self.STAGES)
        step = rect.width() / n
        cy = 16
        radius = 6
        accent = QColor(COLORS["accent"])
        done = QColor(COLORS["ok"])
        pending = QColor(COLORS["border_light"])

        # 连接线
        painter.setPen(QPen(QColor(COLORS["border_light"]), 2))
        for i in range(n - 1):
            x1 = int(step * i + step / 2 + radius + 4)
            x2 = int(step * (i + 1) + step / 2 - radius - 4)
            painter.drawLine(x1, cy, x2, cy)

        for i, name in enumerate(self.STAGES):
            cx = int(step * i + step / 2)
            if i < self._stage:
                painter.setBrush(done)
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QRect(cx - radius, cy - radius, radius * 2, radius * 2))
            elif i == self._stage:
                halo = radius + 4 + 3 * float(math.sin(self._pulse))
                painter.setBrush(QColor(76, 141, 255, 40))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QRect(int(cx - halo), int(cy - halo),
                                         int(halo * 2), int(halo * 2)))
                painter.setBrush(accent)
                painter.drawEllipse(QRect(cx - radius, cy - radius, radius * 2, radius * 2))
            else:
                painter.setBrush(Qt.NoBrush)
                pen = QPen(pending, 2)
                painter.setPen(pen)
                painter.drawEllipse(QRect(cx - radius, cy - radius, radius * 2, radius * 2))

            if i < self._stage:
                color = QColor(COLORS["text_dim"])
            elif i == self._stage:
                color = accent
            else:
                color = QColor(COLORS["text_mute"])
            painter.setPen(QPen(color))
            painter.setFont(QFont("Microsoft YaHei UI", 9))
            painter.drawText(QRect(int(cx - step / 2), cy + 12, int(step), 18),
                             Qt.AlignCenter, name)


class ElidedLabel(QLabel):
    """按当前可用宽度自动省略文本。

    自绘而不是改 QLabel 的 text：QLabel.setText 会触发 updateGeometry，
    在会 resize 的布局里容易形成 回环 -> 栈溢出。
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumHeight(20)
        self.setToolTip(text)

    def setText(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self.update()

    def full_text(self) -> str:
        return self._full

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        metrics = QFontMetrics(self.font())
        elided = metrics.elidedText(self._full, Qt.ElideMiddle, max(20, self.width() - 4))
        painter.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter, elided)


class ModelPicker(QWidget):
    """用复选框挑模型：可多选，按勾选顺序使用，失败时自动切下一个。"""

    selectionChanged = pyqtSignal(list)

    def __init__(self, parent=None, max_height: int = 168):
        super().__init__(parent)
        self._models: list[str] = []
        self._selected: list[str] = []
        self._rows: dict[str, QCheckBox] = {}
        self._build(max_height)

    def _build(self, max_height: int):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("筛选模型…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        top.addWidget(self.search, 1)
        self.count_label = QLabel("未获取")
        self.count_label.setObjectName("hint")
        top.addWidget(self.count_label)
        lay.addLayout(top)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.host = QWidget()
        self.host_lay = QVBoxLayout(self.host)
        self.host_lay.setContentsMargins(0, 0, 0, 0)
        self.host_lay.setSpacing(2)
        self.host_lay.addStretch(1)
        self.scroll.setWidget(self.host)
        self._max_height = max_height
        self.scroll.setFixedHeight(72)
        lay.addWidget(self.scroll)

        self.empty = QLabel("还没有模型列表——点「拉取模型列表」获取后可勾选")
        self.empty.setObjectName("hint")
        self.empty.setWordWrap(True)
        lay.addWidget(self.empty)

    # --------------------------------------------------------------- data
    def set_models(self, models: list[str], selected: list[str]) -> None:
        self._models = list(dict.fromkeys([str(m) for m in models if m]))
        for name in selected:
            if name not in self._models:
                self._models.append(name)
        self._selected = [m for m in selected if m in self._models]
        self._rebuild()

    def selected_models(self) -> list[str]:
        return list(self._selected)

    def _rebuild(self):
        while self.host_lay.count() > 1:
            item = self.host_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._rows = {}
        self._filter()
        # 重建后回到列表顶部，避免停留在上一轮的滚动位置
        bar = self.scroll.verticalScrollBar()
        if bar is not None:
            bar.setValue(0)

    def _filter(self):
        keyword = self.search.text().strip().lower()
        shown = 0
        for name in self._models:
            entry = self._rows.get(name)
            if entry is None:
                entry = self._make_row(name)
                self._rows[name] = entry
                self.host_lay.insertWidget(self.host_lay.count() - 1, entry[0])
            visible = not keyword or keyword in name.lower()
            entry[0].setVisible(visible)
            if visible:
                shown += 1
        self.empty.setVisible(not self._models)
        self.scroll.setVisible(bool(self._models))
        # 列表高度跟着条目数走：少的时候不占地方，多的时候最多到 max_height 后滚动
        row_h = 27
        self.scroll.setFixedHeight(min(self._max_height, max(30, shown * row_h + 6)))
        if not self._models:
            self.count_label.setText("未获取")
        else:
            self.count_label.setText(f"{shown}/{len(self._models)} 个")
        self._sync_rows()

    def _make_row(self, name: str):
        row = QWidget()
        row.setObjectName("modelRow")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.setSpacing(8)

        box = QCheckBox()
        box.setObjectName("modelItem")
        box.setToolTip(name)
        box.setChecked(name in self._selected)
        box.toggled.connect(lambda checked, n=name: self._on_toggled(n, checked))
        lay.addWidget(box)

        badge = QLabel("")
        badge.setObjectName("modelBadge")
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedWidth(18)
        badge.setVisible(False)
        lay.addWidget(badge)

        label = ElidedLabel(name)
        label.setObjectName("modelName")
        lay.addWidget(label, 1)
        return row, box, badge

    def _on_toggled(self, name: str, checked: bool):
        if checked:
            if name not in self._selected:
                self._selected.append(name)
        else:
            self._selected = [m for m in self._selected if m != name]
        self._sync_rows()
        self.selectionChanged.emit(list(self._selected))

    def _sync_rows(self):
        """把勾选顺序画成优先级角标：1 是主用模型，后面是备用。"""
        for name, entry in self._rows.items():
            box, badge = entry[1], entry[2]
            idx = self._selected.index(name) if name in self._selected else -1
            if idx >= 0:
                badge.setText(str(idx + 1))
                badge.setVisible(True)
                box.setStyleSheet(
                    f"QCheckBox#modelItem:checked {{ color: {COLORS['accent']}; }}"
                    if idx == 0 else "")
            else:
                badge.setVisible(False)
                badge.setText("")
                box.setStyleSheet("")

    def set_selection(self, selected: list[str]) -> None:
        selected = [m for m in selected if m]
        for name in selected:
            if name not in self._models:
                self._models.append(name)
                entry = self._make_row(name)
                self._rows[name] = entry
                self.host_lay.insertWidget(self.host_lay.count() - 1, entry[0])
        self._selected = [m for m in selected if m in self._models]
        for name, entry in self._rows.items():
            block = entry[1].blockSignals(True)
            entry[1].setChecked(name in self._selected)
            entry[1].blockSignals(block)
        self._sync_rows()
        self._filter()

    def highlight_primary(self) -> str:
        return self._selected[0] if self._selected else ""



IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")


class ImageDropStrip(QWidget):
    """参考图区域：支持按钮上传，也支持从文件管理器直接拖进来。"""

    changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paths: list[str] = []
        self.setAcceptDrops(True)
        self.setMinimumHeight(78)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.hint = QLabel("还没有参考图：点「上传参考图」或把图片拖到这里")
        self.hint.setObjectName("hint")
        self.hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.hint)

        self.row = QHBoxLayout()
        self.row.setSpacing(8)
        lay.addLayout(self.row)
        self._rebuild()

    # ------------------------------------------------------------------ data
    def paths(self) -> list[str]:
        return list(self._paths)

    def count(self) -> int:
        return len(self._paths)

    def add_files(self, paths) -> int:
        added = 0
        for path in paths or []:
            path = str(path)
            if not os.path.exists(path):
                continue
            if Path(path).suffix.lower() not in IMAGE_SUFFIXES:
                continue
            if any(os.path.normcase(path) == os.path.normcase(p) for p in self._paths):
                continue
            if len(self._paths) >= 6:
                break
            self._paths.append(path)
            added += 1
        if added:
            self._rebuild()
            self.changed.emit(self.paths())
        return added

    def remove_at(self, index: int):
        if 0 <= index < len(self._paths):
            self._paths.pop(index)
            self._rebuild()
            self.changed.emit(self.paths())

    def clear(self):
        if not self._paths:
            return
        self._paths = []
        self._rebuild()
        self.changed.emit([])

    def _rebuild(self):
        while self.row.count():
            item = self.row.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.hint.setVisible(not self._paths)
        for index, path in enumerate(self._paths):
            self.row.addWidget(self._make_item(path, index))
        self.row.addStretch(1)
        self.setFixedHeight(30 if not self._paths else 92)

    def _make_item(self, path: str, index: int):
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        thumb = QLabel()
        thumb.setFixedSize(66, 66)
        thumb.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            thumb.setPixmap(pixmap.scaled(66, 66, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        thumb.setStyleSheet(
            f"QLabel{{background:{COLORS['surface2']};border:1px solid {COLORS['border_light']};"
            f"border-radius:6px;}}")
        thumb.setToolTip(path)
        lay.addWidget(thumb)

        remove = QPushButton("移除")
        remove.setObjectName("chip")
        remove.setFixedHeight(20)
        remove.setCursor(Qt.PointingHandCursor)
        remove.clicked.connect(lambda: self.remove_at(index))
        lay.addWidget(remove)
        return host

    # ------------------------------------------------------------ drag/drop
    @staticmethod
    def _image_urls(mime) -> list[str]:
        if not mime.hasUrls():
            return []
        files = []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            if Path(path).suffix.lower() in IMAGE_SUFFIXES:
                files.append(path)
        return files

    def dragEnterEvent(self, event):
        if self._image_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._image_urls(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = self._image_urls(event.mimeData())
        if files:
            self.add_files(files)
            event.acceptProposedAction()
        else:
            event.ignore()


class DeveloperDialog(QDialog):
    """开发者信息弹窗：单独一个按钮打开，不打扰主界面。"""

    def __init__(self, parent=None, app_title: str = "", version: str = "",
                 developer: str = "", qq: str = "", endpoint_label: str = "",
                 endpoint_url: str = ""):
        super().__init__(parent)
        self.setWindowTitle("开发者信息")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setStyleSheet(
            f"QDialog{{background:{COLORS['bg']};}}"
            f"QLabel{{color:{COLORS['text']};}}"
            f"QLabel#muted{{color:{COLORS['text_mute']};font-size:12px;}}"
            f"QLabel#key{{color:{COLORS['text_mute']};font-size:12px;}}"
            f"QLabel#val{{color:{COLORS['text']};font-size:14px;font-weight:600;}}"
            f"QLabel#title{{color:{COLORS['text']};font-size:15px;font-weight:700;}}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)

        title = QLabel(app_title)
        title.setObjectName("title")
        title.setWordWrap(True)
        lay.addWidget(title)

        ver = QLabel(f"版本 {version}")
        ver.setObjectName("muted")
        lay.addWidget(ver)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background:{COLORS['border_light']};border:none;")
        lay.addWidget(line)

        self._add_row(lay, "开发者", developer)
        self._add_row(lay, "QQ", qq, copy_value=qq)

        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setStyleSheet(f"background:{COLORS['border_light']};border:none;")
        lay.addWidget(line2)

        self._add_row(lay, "中转站", f"{endpoint_label} · {endpoint_url}")

        note = QLabel("本工具通过 Bytego 中转站调用 GPT-Image / Grok Image 模型，"
                      "Key 与生成内容均由用户自行保管。")
        note.setObjectName("muted")
        note.setWordWrap(True)
        lay.addWidget(note)

        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("关闭")
        close.setObjectName("ghost")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

    def _add_row(self, lay, key: str, value: str, copy_value: str = ""):
        row = QHBoxLayout()
        row.setSpacing(12)
        k = QLabel(key)
        k.setObjectName("key")
        k.setFixedWidth(64)
        row.addWidget(k)
        v = QLabel(value)
        v.setObjectName("val")
        v.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(v, 1)
        if copy_value:
            btn = QPushButton("复制")
            btn.setObjectName("ghost")
            btn.setFixedHeight(26)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda: self._copy(copy_value))
            row.addWidget(btn)
        lay.addLayout(row)

    def _copy(self, text: str):
        from PyQt5.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(text)
        Toast(self, f"已复制：{text}", "ok")


class ImageDialog(QDialog):
    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("图片预览")
        self.resize(1080, 760)
        self.setStyleSheet(f"QDialog{{background:{COLORS['bg']};}}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        canvas = ImageCanvas(self, 480)
        canvas.set_image(path)
        lay.addWidget(canvas, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        info = QLabel(f"{Path(path).name}   {Path(path).stat().st_size / 1024:.0f} KB"
                      if os.path.exists(path) else Path(path).name)
        info.setObjectName("muted")
        row.addWidget(info)
        btn = QPushButton("关闭")
        btn.setObjectName("ghost")
        btn.clicked.connect(self.accept)
        row.addWidget(btn)
        lay.addLayout(row)


class SwitchBox(QWidget):
    """带标签的开关（用勾选框实现，风格与主题一致）。"""

    toggled = pyqtSignal(bool)

    def __init__(self, text: str, checked: bool = False, hint: str = "", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.box = QPushButton(text, self)
        self.box.setObjectName("ghost")
        self.box.setCheckable(True)
        self.box.setChecked(checked)
        self.box.setCursor(Qt.PointingHandCursor)
        self.box.setFocusPolicy(Qt.NoFocus)
        self.box.toggled.connect(self.toggled.emit)
        lay.addWidget(self.box)
        if hint:
            lbl = QLabel(hint)
            lbl.setObjectName("hint")
            lbl.setWordWrap(True)
            lay.addWidget(lbl)
        self._hint = lbl if hint else None

    def isChecked(self) -> bool:
        return self.box.isChecked()

    def setChecked(self, value: bool) -> None:
        self.box.setChecked(value)


def horizontal(*widgets, spacing: int = 8) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    for w in widgets:
        if isinstance(w, QWidget):
            lay.addWidget(w)
        else:
            lay.addLayout(w)
    return lay
