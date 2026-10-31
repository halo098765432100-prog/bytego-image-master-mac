from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QAbstractSpinBox, QCheckBox, QComboBox, QFileDialog, QGridLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton,
                             QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from ..config import DEVELOPER, DEVELOPER_QQ, ENDPOINTS, endpoint_label, endpoint_url
from ..theme import COLORS
from .widgets import Card, ModelPicker, SectionTitle


class SettingsPage(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.ctrl = controller
        self._loading = False
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        # ------------------------------------------------ API
        api = Card()
        api.add(SectionTitle("中转站线路", "Bytego 固定两个端点，切换后立即生效"))

        self.endpoint_buttons: dict[str, QRadioButton] = {}
        for key, item in ENDPOINTS.items():
            radio = QRadioButton(f"{item['label']}（{item['url']}）")
            radio.setToolTip(item["hint"])
            radio.toggled.connect(lambda checked, k=key: self._on_endpoint(k, checked))
            api.add(radio)
            self.endpoint_buttons[key] = radio

        self.endpoint_hint = QLabel("")
        self.endpoint_hint.setObjectName("hint")
        self.endpoint_hint.setWordWrap(True)
        api.add(self.endpoint_hint)

        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("在 Bytego 控制台申请后粘贴到这里")
        self.api_key.textChanged.connect(self._apply)
        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        key_row.addWidget(self.api_key, 1)
        self.show_key = QPushButton("显示")
        self.show_key.setObjectName("ghost")
        self.show_key.clicked.connect(self._toggle_key)
        key_row.addWidget(self.show_key)
        api.add(self._row("API Key", key_row))
        api.add(QLabel("Key 只保存在本机 config.json，不会外发到 Bytego 以外的任何地方。"))

        btn_row = QHBoxLayout()
        self.test_btn = QPushButton("测试连接")
        self.test_btn.setObjectName("ghost")
        self.test_btn.clicked.connect(self.ctrl.test_connection)
        btn_row.addWidget(self.test_btn)
        self.fetch_btn = QPushButton("拉取模型列表")
        self.fetch_btn.setObjectName("ghost")
        self.fetch_btn.clicked.connect(self.ctrl.fetch_models)
        btn_row.addWidget(self.fetch_btn)
        btn_row.addStretch(1)
        api.add_layout(btn_row)
        lay.addWidget(api)

        # ------------------------------------------------ 默认生成参数
        gen = Card()
        gen.add(SectionTitle("默认生成参数", "新打开软件时生成页的初始值"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        model_title = QLabel("图像模型（可多选，按顺序兜底）")
        model_title.setObjectName("hint")
        gen.add(model_title)
        self.image_model = ModelPicker(self, max_height=150)
        self.image_model.selectionChanged.connect(self._on_model_pick)
        gen.add(self.image_model)

        self.size = QComboBox()
        self.size.setEditable(True)
        self.size.addItems(["4096x4096", "2048x2048", "1536x1024", "1024x1536",
                            "1024x1024", "1792x1024", "1024x1792"])
        self.size.currentTextChanged.connect(self._apply)
        grid.addWidget(self._field("默认尺寸", self.size), 0, 0)

        self.quality = QComboBox()
        for value, label in [("auto", "自动"), ("low", "快速"), ("medium", "标准"),
                             ("high", "精细"), ("xhigh", "超精细"), ("max", "最高")]:
            self.quality.addItem(label, value)
        self.quality.currentIndexChanged.connect(self._apply)
        grid.addWidget(self._field("默认质量", self.quality), 0, 1)

        self.chat_model = QComboBox()
        self.chat_model.setEditable(True)
        self.chat_model.addItems(["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-5", "gpt-5-mini"])
        self.chat_model.currentTextChanged.connect(self._apply)
        grid.addWidget(self._field("Agent 模型", self.chat_model), 0, 2)

        self.count = QSpinBox()
        self.count.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.count.setRange(1, 4)
        self.count.valueChanged.connect(self._apply)
        grid.addWidget(self._field("默认数量", self.count), 1, 0)

        self.fmt = QComboBox()
        self.fmt.addItems(["png", "jpeg", "webp"])
        self.fmt.currentTextChanged.connect(self._apply)
        grid.addWidget(self._field("默认格式", self.fmt), 1, 1)

        self.transparent = QCheckBox("默认透明背景")
        self.transparent.toggled.connect(self._apply)
        grid.addWidget(self._field("背景", self.transparent), 1, 2)
        gen.add_layout(grid)
        lay.addWidget(gen)

        # ------------------------------------------------ 运行与重试
        run = Card()
        run.add(SectionTitle("运行与容错", "接口报错时自动重试的次数与等待策略"))
        grid2 = QGridLayout()
        grid2.setHorizontalSpacing(12)
        grid2.setVerticalSpacing(10)
        self.retries = QSpinBox()
        self.retries.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.retries.setRange(1, 10)
        self.retries.valueChanged.connect(self._apply)
        grid2.addWidget(self._field("重试次数", self.retries), 0, 0)

        self.timeout = QSpinBox()
        self.timeout.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.timeout.setRange(10, 1800)
        self.timeout.setSingleStep(10)
        self.timeout.valueChanged.connect(self._apply)
        grid2.addWidget(self._field("超时秒数", self.timeout), 0, 1)

        self.out_dir = QLineEdit()
        self.out_dir.textChanged.connect(self._apply)
        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        dir_row.addWidget(self.out_dir, 1)
        browse = QPushButton("浏览")
        browse.setObjectName("ghost")
        browse.clicked.connect(self._browse_dir)
        dir_row.addWidget(browse)
        grid2.addWidget(self._field("输出目录", dir_row), 1, 0, 1, 2)
        run.add_layout(grid2)
        run.add(QLabel("提示：重试次数按「总尝试次数」计算，失败后按 1.2s / 2.4s / 3.6s … 递增等待；"
                       "全部失败会在页面弹出完整报错信息，并在底部日志中留档。"))
        lay.addWidget(run)

        # ------------------------------------------------ Agent 权限
        agent = Card()
        agent.add(SectionTitle("Agent 本地权限", "关闭后模型即使调用该工具也会被拒绝"))
        self.allow_command = QCheckBox("允许执行命令行")
        self.allow_write = QCheckBox("允许写入文件")
        self.allow_open = QCheckBox("允许打开路径")
        self.allow_generate = QCheckBox("允许 Agent 触发生成图片")
        self.auto_approve = QCheckBox("危险操作免确认（run_command / write_file 不再弹窗）")
        for box in (self.allow_command, self.allow_write, self.allow_open,
                    self.allow_generate, self.auto_approve):
            box.toggled.connect(self._apply)
            agent.add(box)
        lay.addWidget(agent)

        # ------------------------------------------------ 开发者信息
        about = Card()
        about.add(SectionTitle("开发者", "有问题或定制需求可直接联系"))
        dev_row = QHBoxLayout()
        dev_row.setSpacing(8)
        dev_text = QLabel(f"开发者：{DEVELOPER}　QQ：{DEVELOPER_QQ}")
        dev_text.setObjectName("devLine")
        dev_row.addWidget(dev_text, 1)
        dev_btn = QPushButton("开发者信息")
        dev_btn.setObjectName("ghost")
        dev_btn.setCursor(Qt.PointingHandCursor)
        dev_btn.clicked.connect(self.ctrl.show_developer_info)
        dev_row.addWidget(dev_btn)
        about.add_layout(dev_row)
        about.add(QLabel("本工具通过 Bytego 中转站调用 GPT-Image / Grok Image 模型，"
                         "Key 与生成内容均由用户自行保管。"))
        lay.addWidget(about)

        lay.addStretch(1)
        scroll.setWidget(host)
        root.addWidget(scroll)

        # 与生成页共用同一份模型列表与勾选状态
        self.ctrl.modelsChanged.connect(self.set_models)
        self.ctrl.selectionChanged.connect(self._on_selection_changed)

    def _field(self, label: str, widget) -> QWidget:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lbl = QLabel(label)
        lbl.setObjectName("hint")
        lay.addWidget(lbl)
        if isinstance(widget, QWidget):
            lay.addWidget(widget)
        else:
            lay.addLayout(widget)
        return host

    def _row(self, label: str, widget) -> QWidget:
        host = QWidget()
        lay = QHBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lbl = QLabel(label)
        lbl.setFixedWidth(76)
        lbl.setObjectName("muted")
        lay.addWidget(lbl)
        if isinstance(widget, QWidget):
            lay.addWidget(widget, 1)
        else:
            lay.addLayout(widget, 1)
        return host

    def _toggle_key(self):
        shown = self.api_key.echoMode() == QLineEdit.Password
        self.api_key.setEchoMode(QLineEdit.Normal if shown else QLineEdit.Password)
        self.show_key.setText("隐藏" if shown else "显示")

    def _copy_qq(self):
        from PyQt5.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(DEVELOPER_QQ)
        from .widgets import Toast
        Toast(self, f"已复制 QQ {DEVELOPER_QQ}", "ok")

    def _on_endpoint(self, key: str, checked: bool) -> None:
        if checked:
            self._apply()
            self._refresh_endpoint_hint(key)

    def _refresh_endpoint_hint(self, key: str) -> None:
        item = ENDPOINTS.get(key) or ENDPOINTS[list(ENDPOINTS)[0]]
        self.endpoint_hint.setText(f"当前线路：{endpoint_label(key)} · {endpoint_url(key)} —— {item['hint']}")

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出目录", self.out_dir.text() or "")
        if path:
            self.out_dir.setText(path)

    def _apply(self, *_):
        if self._loading:
            return
        self.ctrl.apply_settings({
            "endpoint": self.current_endpoint(),
            "api_key": self.api_key.text().strip(),
            "chat_model": self.chat_model.currentText().strip(),
            "size": self.size.currentText().strip(),
            "quality": self.quality.currentData(),
            "count": self.count.value(),
            "output_format": self.fmt.currentText().strip(),
            "transparent": self.transparent.isChecked(),
            "max_retries": self.retries.value(),
            "timeout": self.timeout.value(),
            "output_dir": self.out_dir.text().strip(),
            "allow_command": self.allow_command.isChecked(),
            "allow_write": self.allow_write.isChecked(),
            "allow_open": self.allow_open.isChecked(),
            "allow_generate": self.allow_generate.isChecked(),
            "auto_approve": self.auto_approve.isChecked(),
        })

    def current_endpoint(self) -> str:
        for key, radio in self.endpoint_buttons.items():
            if radio.isChecked():
                return key
        return list(ENDPOINTS)[0]

    def _on_model_pick(self, models: list):
        self.ctrl.set_model_selection(models)

    def _on_selection_changed(self, models: list):
        self.image_model.set_selection(models)

    def set_models(self, models: list[str]):
        self.image_model.set_models(models, self.ctrl.model_selection())

    def load_config(self, cfg: dict):
        self._loading = True
        try:
            key = cfg.get("endpoint") if cfg.get("endpoint") in ENDPOINTS else list(ENDPOINTS)[0]
            radio = self.endpoint_buttons.get(key)
            if radio is not None:
                radio.setChecked(True)
            self._refresh_endpoint_hint(key)
            self.api_key.setText(cfg.get("api_key", ""))
            self.chat_model.setCurrentText(cfg.get("chat_model", "gpt-4o"))
            self.size.setCurrentText(cfg.get("size", "4096x4096"))
            idx = self.quality.findData(cfg.get("quality", "auto"))
            self.quality.setCurrentIndex(idx if idx >= 0 else 0)
            self.count.setValue(int(cfg.get("count", 1)))
            self.fmt.setCurrentText(cfg.get("output_format", "png"))
            self.transparent.setChecked(bool(cfg.get("transparent", False)))
            self.retries.setValue(int(cfg.get("max_retries", 5)))
            self.timeout.setValue(int(cfg.get("timeout", 1000)))
            self.out_dir.setText(cfg.get("output_dir", ""))
            self.allow_command.setChecked(bool(cfg.get("allow_command", True)))
            self.allow_write.setChecked(bool(cfg.get("allow_write", True)))
            self.allow_open.setChecked(bool(cfg.get("allow_open", True)))
            self.allow_generate.setChecked(bool(cfg.get("allow_generate", True)))
            self.auto_approve.setChecked(bool(cfg.get("auto_approve", False)))
        finally:
            self._loading = False
