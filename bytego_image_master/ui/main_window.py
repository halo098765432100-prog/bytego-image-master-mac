import os
import sys
import threading
import time
from pathlib import Path

from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QKeySequence, QPixmap
from PyQt5.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
                             QMessageBox, QPlainTextEdit, QPushButton, QShortcut,
                             QStackedWidget, QTextEdit, QVBoxLayout, QWidget)

from ..agent import Agent
from ..agent_tools import ToolRunner
from ..api import ApiClient, ApiError
from ..config import (APP_TITLE, DEVELOPER, DEVELOPER_QQ, ENDPOINTS, VERSION,
                      endpoint_label, endpoint_url, load_config, load_history,
                      save_config, save_history)
from ..theme import COLORS, build_qss
from .pages_agent import AgentPage
from .pages_gallery import GalleryPage
from .pages_generate import GeneratePage
from .pages_settings import SettingsPage
from .widgets import Toast, safe_slot
from .workers import FunctionTask

RES_DIR = Path(__file__).resolve().parent.parent / "resources"


class Bridge(QObject):
    confirm = pyqtSignal(object)
    images = pyqtSignal(object)


class MainWindow(QMainWindow):
    COLORS = COLORS

    modelsChanged = pyqtSignal(list)
    selectionChanged = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.history = load_history()
        self.client = self._build_client()
        self.logs: list[str] = []
        self._pixmap_cache: dict[str, QPixmap] = {}
        self.bridge = Bridge()
        self.bridge.confirm.connect(self._on_confirm)
        self.bridge.images.connect(self.on_images_ready)
        self._tasks: list[FunctionTask] = []
        self.models: list[str] = []

        self.setWindowTitle(APP_TITLE)
        self._fit_window()
        self.setMinimumSize(1100, 700)
        self.setObjectName("root")
        icon = RES_DIR / ("icon.ico" if sys.platform == "win32" else "icon.png")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.setStyleSheet(build_qss())
        self._build_ui()
        self._sync_pages()
        self.log("就绪。中转站：" + endpoint_label(self.cfg.get("endpoint", "")) +
                 " · " + (self.cfg.get("base_url") or ""))

    def _fit_window(self):
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        if not avail:
            self.resize(1320, 840)
            return
        width = min(1400, max(1180, int(avail.width() * 0.78)))
        height = min(920, max(760, int(avail.height() * 0.86)))
        self.resize(width, height)

    # ------------------------------------------------------------------ ui
    def _build_ui(self):
        central = QWidget()
        central.setObjectName("root")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 侧边栏
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(214)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 18, 14, 14)
        sl.setSpacing(6)

        brand = QLabel("Bytego")
        brand.setObjectName("brandTitle")
        sl.addWidget(brand)
        sub = QLabel("GPT-IMAGE / GROK IMAGE")
        sub.setObjectName("brandSub")
        sl.addWidget(sub)
        sl.addSpacing(18)

        self.nav_buttons = []
        for text, page in [("生成图片", 0), ("作品库", 1), ("本地 Agent", 2), ("设置", 3)]:
            btn = NavButtonProxy(text)
            btn.clicked.connect(lambda _, i=page: self.switch_page(i))
            sl.addWidget(btn)
            self.nav_buttons.append(btn)
        sl.addStretch(1)

        self.api_pill = QLabel("●  未配置 API")
        self.api_pill.setObjectName("statusPill")
        self.api_pill.setAlignment(Qt.AlignCenter)
        sl.addWidget(self.api_pill)

        self.dev_btn = QPushButton("开发者信息")
        self.dev_btn.setObjectName("ghost")
        self.dev_btn.setMinimumHeight(30)
        self.dev_btn.setCursor(Qt.PointingHandCursor)
        self.dev_btn.setToolTip(f"开发者 {DEVELOPER} · QQ {DEVELOPER_QQ}")
        self.dev_btn.clicked.connect(self.show_developer_info)
        sl.addWidget(self.dev_btn)

        ver = QLabel(f"v{VERSION}")
        ver.setObjectName("hint")
        ver.setAlignment(Qt.AlignCenter)
        sl.addWidget(ver)
        root.addWidget(side)

        # ---- 内容区
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(16, 16, 16, 0)
        cl.setSpacing(0)

        self.stack = QStackedWidget()
        self.page_generate = GeneratePage(self)
        self.page_gallery = GalleryPage(self)
        self.page_agent = AgentPage(self)
        self.page_settings = SettingsPage(self)
        for page in (self.page_generate, self.page_gallery, self.page_agent, self.page_settings):
            self.stack.addWidget(page)
        cl.addWidget(self.stack, 1)

        bar = QFrame()
        bar.setObjectName("bottomBar")
        bar.setFixedHeight(38)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(14, 0, 12, 0)
        bl.setSpacing(10)
        self.log_label = QLabel("就绪")
        self.log_label.setObjectName("hint")
        bl.addWidget(self.log_label, 1)
        clear_btn = QPushButton("清空日志")
        clear_btn.setObjectName("ghost")
        clear_btn.setFixedHeight(26)
        clear_btn.clicked.connect(self._clear_logs)
        bl.addWidget(clear_btn)
        view_btn = QPushButton("查看日志")
        view_btn.setObjectName("ghost")
        view_btn.setFixedHeight(26)
        view_btn.clicked.connect(self._show_logs)
        bl.addWidget(view_btn)
        cl.addWidget(bar)
        root.addWidget(content, 1)

        self.setCentralWidget(central)
        self.nav_buttons[0].setChecked(True)
        self.switch_page(0)

        for index in range(4):
            QShortcut(QKeySequence(f"Ctrl+{index + 1}"), self,
                      activated=lambda i=index: self.switch_page(i))

    def switch_page(self, index: int):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)

    def _sync_pages(self):
        self.page_generate.load_config(self.cfg)
        self.page_agent.load_config(self.cfg)
        self.page_settings.load_config(self.cfg)
        self.page_generate.set_models(self.models)
        self.page_settings.set_models(self.models)
        self.page_gallery.refresh()
        self._update_pill()

    def _update_pill(self):
        if self.cfg.get("api_key"):
            self.api_pill.setText("●  API 已配置")
            self.api_pill.setStyleSheet(f"color:{COLORS['ok']};")
        else:
            self.api_pill.setText("●  未配置 API")
            self.api_pill.setStyleSheet(f"color:{COLORS['warn']};")

    # ----------------------------------------------------------- settings
    def apply_settings(self, updates: dict):
        changed = False
        endpoint_changed = False
        for key, value in updates.items():
            if key == "base_url":
                continue  # base url 由线路决定，不接受外部覆盖
            if key == "endpoint":
                new_key = value if value in ENDPOINTS else list(ENDPOINTS)[0]
                if self.cfg.get("endpoint") != new_key:
                    self.cfg["endpoint"] = new_key
                    endpoint_changed = True
                continue
            if self.cfg.get(key) != value:
                self.cfg[key] = value
                if key in ("api_key", "timeout", "max_retries"):
                    changed = True
        if endpoint_changed:
            key = self.cfg["endpoint"]
            override = (os.environ.get("BYTEGO_BASE_URL") or "").strip()
            url = override or endpoint_url(key)
            if self.cfg.get("base_url") != url:
                self.cfg["base_url"] = url
                changed = True
            self.log(f"中转站线路：{endpoint_label(key)} · {url}")
        save_config(self.cfg)
        if changed:
            self.client = self._build_client()
        self._update_pill()

    def set_permission(self, key: str, value: bool):
        self.cfg[key] = value
        save_config(self.cfg)

    # --------------------------------------------------------------- models
    def model_selection(self) -> list[str]:
        return [str(m) for m in (self.cfg.get("image_models") or []) if m]

    def set_model_selection(self, models: list[str]) -> None:
        models = [str(m) for m in models if m]
        if self.cfg.get("image_models") != models:
            self.cfg["image_models"] = models
            if models:
                self.cfg["image_model"] = models[0]
            save_config(self.cfg)
        self.selectionChanged.emit(models)

    def set_models(self, models: list[str]) -> None:
        self.models = list(dict.fromkeys([str(m) for m in models if m]))
        self.modelsChanged.emit(self.models)

    def current_model(self) -> str:
        picked = self.model_selection()
        if picked:
            return picked[0]
        return self.cfg.get("image_model") or "gpt-image-2"

    # ----------------------------------------------------------- 复用提示词
    def use_prompt(self, text: str) -> None:
        if not text:
            return
        self.switch_page(0)
        self.page_generate.set_prompt(text)
        self.log("已把作品库的提示词填入生成页")

    def _build_client(self) -> ApiClient:
        return ApiClient(self.cfg.get("base_url", ""), self.cfg.get("api_key", ""),
                         timeout=int(self.cfg.get("timeout", 180)),
                         max_retries=int(self.cfg.get("max_retries", 5)))

    def build_client(self) -> ApiClient:
        """每次生成单独建一个客户端，取消时不会影响其它请求。"""
        return self._build_client()

    # -------------------------------------------------------------- images
    @safe_slot
    def on_images_ready(self, results):
        if not results:
            return
        for res in results:
            self.history.insert(0, res.to_dict() if hasattr(res, "to_dict") else dict(res))
        self.history = self.history[:300]
        save_history(self.history)
        self.page_gallery.refresh()

    def remove_history(self, item: dict):
        self.history = [h for h in self.history if h.get("path") != item.get("path")]
        save_history(self.history)
        self.page_gallery.refresh()

    def pixmap_for(self, path: str, width: int, height: int = 0) -> QPixmap:
        if not path or not os.path.exists(path):
            return QPixmap()
        key = f"{path}|{width}|{height}"
        cached = self._pixmap_cache.get(key)
        if cached is not None:
            return cached
        pix = QPixmap(path)
        if pix.isNull():
            return QPixmap()
        if height:
            pix = pix.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            pix = pix.scaledToWidth(width, Qt.SmoothTransformation)
        self._pixmap_cache[key] = pix
        return pix

    def open_output_dir(self):
        path = Path(self.cfg.get("output_dir") or ".")
        try:
            path.mkdir(parents=True, exist_ok=True)
            from ..platforms import open_in_file_manager
            open_in_file_manager(path)
        except Exception as exc:
            self.log(f"打开目录失败：{exc}")

    # --------------------------------------------------------------- agent
    def build_agent(self, model: str, system_prompt: str) -> Agent:
        client = self._build_client()
        runner = ToolRunner(
            self.cfg,
            confirm=self.confirm_tool,
            generate_fn=self._agent_generate,
            history_fn=lambda n: self.history[:n],
        )
        return Agent(client, runner, model=model, system_prompt=system_prompt)

    def _agent_generate(self, prompt: str, size: str, quality: str, count: int):
        client = self._build_client()
        results = client.generate_image(
            prompt=prompt, model=self.cfg.get("image_model", "gpt-image-2"),
            size=size, quality=quality, count=count,
            output_format=self.cfg.get("output_format", "png"),
            transparent=bool(self.cfg.get("transparent", False)),
            output_dir=self.cfg.get("output_dir", ""),
            on_retry=lambda attempt, err: self.log(f"[重试 {attempt}] {err.display()}"),
        )
        self.bridge.images.emit(results)
        return results

    def confirm_tool(self, name: str, args: dict) -> bool:
        if self.cfg.get("auto_approve"):
            return True
        box = {"result": False}
        event = threading.Event()

        def ask(ok: bool):
            box["result"] = ok
            event.set()

        self.bridge.confirm.emit((name, args, ask))
        event.wait(300)
        return bool(box["result"])

    @safe_slot
    def _on_confirm(self, payload):
        name, args, ask = payload
        text = "\n".join(f"{k}: {v}" for k, v in (args or {}).items())
        reply = QMessageBox.question(
            self, "确认本地操作",
            f"Agent 请求执行本地工具「{name}」，是否允许？\n\n{text[:1200]}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        ask(reply == QMessageBox.Yes)

    # ------------------------------------------------------------ settings
    def show_developer_info(self):
        """单独一个按钮：查看开发者信息。"""
        from .widgets import DeveloperDialog
        key = self.cfg.get("endpoint", "")
        dialog = DeveloperDialog(self, app_title=APP_TITLE, version=VERSION,
                                 developer=DEVELOPER, qq=DEVELOPER_QQ,
                                 endpoint_label=endpoint_label(key),
                                 endpoint_url=endpoint_url(key))
        dialog.exec_()

    def test_connection(self):
        self.log("正在测试连接…")

        def job():
            try:
                models = self.client.list_models()
                return {"ok": True, "models": models}
            except ApiError as exc:
                return {"ok": False, "error": exc.display()}

        task = FunctionTask(job)
        task.done.connect(self._test_done)
        self._tasks.append(task)
        task.start()

    @safe_slot
    def _test_done(self, result: dict):
        if result.get("ok"):
            models = result.get("models", [])
            self.log(f"连接成功，可用模型 {len(models)} 个")
            Toast(self, f"连接成功（{len(models)} 个模型）", "ok")
            self.set_models(models)
            if models:
                self.page_settings.image_model.set_models(models, self.model_selection())
                self.page_generate.set_models(models)
        else:
            self.log("连接失败：" + result.get("error", ""))
            self.show_error("连接失败", result.get("error", ""))

    def fetch_models(self):
        self.test_connection()

    # ---------------------------------------------------------------- misc
    def log(self, message: str):
        stamp = time.strftime("%H:%M:%S")
        line = f"[{stamp}] {message}"
        self.logs.append(line)
        if len(self.logs) > 800:
            self.logs = self.logs[-800:]
        self.log_label.setText(message.replace("\n", " ")[:160])

    def _clear_logs(self):
        self.logs = []
        self.log_label.setText("日志已清空")

    def _show_logs(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("运行日志")
        dialog.resize(820, 520)
        dialog.setStyleSheet(f"QDialog{{background:{COLORS['bg']};}}")
        lay = QVBoxLayout(dialog)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText("\n".join(self.logs))
        lay.addWidget(view)
        close = QPushButton("关闭")
        close.setObjectName("ghost")
        close.clicked.connect(dialog.accept)
        lay.addWidget(close)
        dialog.exec_()

    def show_error(self, title: str, message: str):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Critical)
        box.setText(title)
        box.setInformativeText(message[:900])
        box.setDetailedText(message)
        box.setStandardButtons(QMessageBox.Ok)
        box.exec_()

    def closeEvent(self, event):
        for task in list(self._tasks):
            if task.isRunning():
                task.terminate()
        super().closeEvent(event)


def NavButtonProxy(text: str):
    from .widgets import NavButton
    return NavButton(text)


def enable_dark_titlebar(win):
    if sys.platform != "win32":
        return  # macOS/Linux 深色标题栏交给系统主题
    try:
        import ctypes
        hwnd = int(win.winId())
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), 4)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), 4)
    except Exception:
        pass
