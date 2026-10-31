import json
import threading
from typing import Optional

from PyQt5.QtCore import QMetaObject, Qt, Q_ARG, pyqtSignal
from PyQt5.QtGui import QFont, QGuiApplication, QKeySequence
from PyQt5.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QPlainTextEdit,
                             QPushButton, QScrollArea, QShortcut, QTextEdit, QVBoxLayout,
                             QWidget)

from ..agent import SYSTEM_PROMPT
from ..agent_tools import TOOLS
from .widgets import SectionTitle, Toast, safe_slot
from .workers import AgentTask

TOOL_LABELS = {
    "run_command": "执行命令行",
    "read_file": "读取文件",
    "write_file": "写入文件",
    "list_directory": "浏览目录",
    "open_path": "打开路径",
    "generate_image": "生成图片",
    "list_history": "查看历史",
}


class AgentPage(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.ctrl = controller
        self.task: Optional[AgentTask] = None
        self.messages: list = []
        self._stream_label: Optional[QLabel] = None
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        # ---------------- 对话区
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("本地 Agent")
        title.setObjectName("sectionTitle")
        head.addWidget(title)
        sub = QLabel("用 GPT 模型驱动本机操作：命令、文件、图片生成")
        sub.setObjectName("hint")
        head.addWidget(sub)
        head.addStretch(1)
        self.state = QLabel("就绪")
        self.state.setObjectName("hint")
        head.addWidget(self.state)
        left_lay.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.host = QWidget()
        self.flow = QVBoxLayout(self.host)
        self.flow.setContentsMargins(0, 0, 0, 0)
        self.flow.setSpacing(10)
        self.flow.addStretch(1)
        self.scroll.setWidget(self.host)
        left_lay.addWidget(self.scroll, 1)

        input_card = QFrame()
        input_card.setObjectName("card")
        input_lay = QVBoxLayout(input_card)
        input_lay.setContentsMargins(12, 10, 12, 12)
        input_lay.setSpacing(8)
        self.input = QTextEdit()
        self.input.setPlaceholderText("例如：查一下本机公网 IP 并保存到 D:\\ip.txt，然后生成一张赛博朋克风格的城市图")
        self.input.setFixedHeight(74)
        self.input.setFont(QFont("Microsoft YaHei UI", 10))
        input_lay.addWidget(self.input)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("ghost")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        btn_row.addWidget(self.stop_btn)
        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("primary")
        self.send_btn.setMinimumWidth(110)
        self.send_btn.clicked.connect(self.send)
        btn_row.addWidget(self.send_btn)
        input_lay.addLayout(btn_row)
        QShortcut(QKeySequence("Ctrl+Return"), self.input, activated=self.send)
        left_lay.addWidget(input_card)
        root.addWidget(left, 1)

        # ---------------- 右侧面板
        panel = QFrame()
        panel.setObjectName("card")
        panel.setFixedWidth(286)
        p = QVBoxLayout(panel)
        p.setContentsMargins(16, 14, 16, 16)
        p.setSpacing(10)

        p.addWidget(SectionTitle("Agent 模型", "用于理解指令并决定调用哪些本地工具"))
        self.model_box = QComboBox()
        self.model_box.setEditable(True)
        self.model_box.addItems(["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-5", "gpt-5-mini"])
        p.addWidget(self.model_box)

        p.addWidget(SectionTitle("本地权限", "关闭后对应工具会被模型视为不可用"))
        self.sw_command = self._switch("允许执行命令行", "allow_command")
        self.sw_write = self._switch("允许写入文件", "allow_write")
        self.sw_open = self._switch("允许打开路径", "allow_open")
        self.sw_generate = self._switch("允许 Agent 触发生成", "allow_generate")
        p.addWidget(self.sw_command)
        p.addWidget(self.sw_write)
        p.addWidget(self.sw_open)
        p.addWidget(self.sw_generate)

        self.sw_auto = QPushButton("危险操作免确认")
        self.sw_auto.setObjectName("ghost")
        self.sw_auto.setCheckable(True)
        self.sw_auto.setToolTip("开启后 run_command / write_file 不再弹窗确认")
        self.sw_auto.toggled.connect(lambda v: self.ctrl.set_permission("auto_approve", v))
        p.addWidget(self.sw_auto)

        p.addWidget(SectionTitle("系统提示词", "决定 Agent 的行为边界"))
        self.system_prompt = QPlainTextEdit()
        self.system_prompt.setPlainText(SYSTEM_PROMPT)
        self.system_prompt.setFixedHeight(150)
        self.system_prompt.setFont(QFont("Microsoft YaHei UI", 9))
        p.addWidget(self.system_prompt)

        tools_label = QLabel("可用工具：" + "、".join(TOOL_LABELS.get(t["function"]["name"], t["function"]["name"])
                                                  for t in TOOLS))
        tools_label.setObjectName("hint")
        tools_label.setWordWrap(True)
        p.addWidget(tools_label)
        p.addStretch(1)
        root.addWidget(panel)

    def _switch(self, text: str, key: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("ghost")
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setProperty("cfg_key", key)
        btn.toggled.connect(lambda v, k=key: self.ctrl.set_permission(k, v))
        return btn

    def load_config(self, cfg: dict):
        self.model_box.setCurrentText(cfg.get("chat_model", "gpt-4o"))
        self.sw_command.setChecked(bool(cfg.get("allow_command", True)))
        self.sw_write.setChecked(bool(cfg.get("allow_write", True)))
        self.sw_open.setChecked(bool(cfg.get("allow_open", True)))
        self.sw_generate.setChecked(bool(cfg.get("allow_generate", True)))
        self.sw_auto.setChecked(bool(cfg.get("auto_approve", False)))

    # --------------------------------------------------------------- chat
    def send(self):
        text = self.input.toPlainText().strip()
        if not text:
            return
        if self.task and self.task.isRunning():
            return
        self.input.clear()
        self._add_user(text)
        self.messages.append({"role": "user", "content": text})
        self._stream_label = None
        self.state.setText("思考中…")
        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        agent = self.ctrl.build_agent(self.model_box.currentText().strip(),
                                      self.system_prompt.toPlainText().strip() or SYSTEM_PROMPT)
        task = AgentTask(agent, text, self.messages[:-1])
        task.event.connect(self._on_event)
        task.failed.connect(self._on_failed)
        task.finished.connect(self._on_finished)
        self.task = task
        task.start()

    def _stop(self):
        if self.task and self.task.isRunning():
            self.task.terminate()
            self.task.wait(1500)
        self.state.setText("已停止")
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _on_finished(self):
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if self.state.text() == "思考中…":
            self.state.setText("就绪")

    @safe_slot
    def _on_failed(self, message: str):
        self.state.setText("出错")
        self._add_error(message)
        self.ctrl.log("Agent 失败：" + message)

    @safe_slot
    def _on_event(self, evt: dict):
        kind = evt.get("type")
        if kind == "text":
            if self._stream_label is None:
                self._stream_label = self._add_assistant()
            self._stream_label.setText(self._stream_label.text() + evt.get("text", ""))
            self._stream_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._scroll_bottom()
        elif kind == "tool_start":
            self.state.setText(f"执行工具 {TOOL_LABELS.get(evt.get('name', ''), evt.get('name', ''))} …")
        elif kind == "tool_end":
            self._add_tool(evt)
            if evt.get("ok"):
                self._stream_label = None
            self.state.setText("思考中…")
        elif kind == "retry":
            self.ctrl.log(f"[重试 {evt.get('attempt')}] {evt.get('message')}")
            self.state.setText(f"请求失败，正在重试（{evt.get('attempt')}）…")
        elif kind == "error":
            self._add_error(evt.get("message", ""))
            self.state.setText("出错")

    # ------------------------------------------------------------ bubbles
    def _scroll_bottom(self):
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _add_user(self, text: str):
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bubble.setStyleSheet(
            f"background:{self.ctrl.COLORS['accent_soft']};border:1px solid {self.ctrl.COLORS['accent']};"
            f"border-radius:10px;padding:9px 12px;color:{self.ctrl.COLORS['text']};")
        bubble.setMaximumWidth(520)
        row.addStretch(1)
        row.addWidget(bubble)
        self._append(wrap)

    def _add_assistant(self) -> QLabel:
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        bubble = QLabel("")
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bubble.setStyleSheet(
            f"background:{self.ctrl.COLORS['surface2']};border:1px solid {self.ctrl.COLORS['border']};"
            f"border-radius:10px;padding:9px 12px;color:{self.ctrl.COLORS['text']};")
        bubble.setMaximumWidth(560)
        row.addWidget(bubble)
        row.addStretch(1)
        self._append(wrap)
        return bubble

    def _add_tool(self, evt: dict):
        name = evt.get("name", "")
        args = evt.get("args", {})
        ok = evt.get("ok", False)
        result = str(evt.get("result", ""))
        frame = QFrame()
        frame.setObjectName("cardFlat")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(11, 9, 11, 10)
        lay.setSpacing(5)
        head = QHBoxLayout()
        head.addWidget(QLabel("⚙ " + TOOL_LABELS.get(name, name)))
        head.addStretch(1)
        status = QLabel("已执行" if ok else "未执行")
        status.setStyleSheet(f"color:{self.ctrl.COLORS['ok'] if ok else self.ctrl.COLORS['danger']};"
                             "font-size:11px;")
        head.addWidget(status)
        lay.addLayout(head)
        arg_text = json.dumps(args, ensure_ascii=False, indent=2)[:1200]
        arg_label = QLabel(arg_text)
        arg_label.setWordWrap(True)
        arg_label.setFont(QFont("Consolas", 9))
        arg_label.setStyleSheet(f"color:{self.ctrl.COLORS['text_dim']};")
        lay.addWidget(arg_label)
        res_label = QLabel(result[:1600])
        res_label.setWordWrap(True)
        res_label.setFont(QFont("Consolas", 9))
        res_label.setStyleSheet(f"color:{self.ctrl.COLORS['text_mute']};")
        lay.addWidget(res_label)
        self._append(frame)

    def _add_error(self, message: str):
        frame = QFrame()
        frame.setObjectName("cardFlat")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(11, 9, 11, 10)
        lbl = QLabel("✕ " + message)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{self.ctrl.COLORS['danger']};font-size:12px;")
        lay.addWidget(lbl)
        self._append(frame)

    def _append(self, widget: QWidget):
        self.flow.insertWidget(self.flow.count() - 1, widget)
        self._scroll_bottom()
