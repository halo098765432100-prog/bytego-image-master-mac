import time

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QIcon, QKeySequence
from PyQt5.QtWidgets import (QAbstractSpinBox, QCheckBox, QComboBox, QFileDialog, QGridLayout,
                             QHBoxLayout, QLabel, QMenu, QPlainTextEdit, QProgressBar,
                             QPushButton, QScrollArea, QShortcut, QSizePolicy, QSpinBox,
                             QSplitter, QVBoxLayout, QWidget)

from .widgets import (Card, ElidedLabel, ImageCanvas, ImageDialog, ImageDropStrip, ModelPicker,
                      SectionTitle, StageStepper, Toast, safe_slot)
from .workers import GenerateTask

STYLE_PRESETS = ["电影感光影", "写实摄影", "插画风格", "赛博朋克", "水彩画", "3D 渲染", "动漫二次元", "极简海报"]

SIZES = ["4096x4096", "2048x2048", "1536x1024", "1024x1536", "1024x1024", "1792x1024", "1024x1792"]
QUALITIES = [("auto", "自动"), ("low", "快速"), ("medium", "标准"), ("high", "精细"),
             ("xhigh", "超精细"), ("max", "最高")]
FORMATS = ["png", "jpeg", "webp"]

# 生成过程中的阶段（与 StageStepper 的顺序一致）
STAGE_PREPARE, STAGE_CONNECT, STAGE_DRAW, STAGE_SAVE, STAGE_DONE = range(5)
STAGE_PROGRESS = {STAGE_PREPARE: 6, STAGE_CONNECT: 22, STAGE_DRAW: 78,
                  STAGE_SAVE: 94, STAGE_DONE: 100}

DRAW_HINTS = ["正在理解你的提示词…", "正在构图与配色…", "正在渲染光影细节…",
              "正在输出高分辨率成图…", "马上就好，再等一下…"]


class GeneratePage(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.ctrl = controller
        self.task: GenerateTask | None = None
        self.results = []
        self._client = None
        self._base_status = "就绪"
        self._started_at = 0.0
        self._stage = -1
        self._progress = 0.0
        self._progress_target = 0.0
        self._build()
        self._tick = QTimer(self)
        self._tick.setInterval(100)
        self._tick.timeout.connect(self._on_tick)

    # ------------------------------------------------------------------ ui
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(10)
        split.setObjectName("split")
        root.addWidget(split)

        # --- 左侧：输入 + 参数（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(340)
        scroll.setMinimumHeight(240)
        scroll_host = QWidget()
        left = QVBoxLayout(scroll_host)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(12)

        # --- 提示词
        prompt_card = Card()
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(QLabel("提示词"))
        self.counter = QLabel("0 字")
        self.counter.setObjectName("hint")
        head.addWidget(self.counter)
        head.addStretch(1)

        self.style_btn = QPushButton("风格标签")
        self.style_btn.setObjectName("ghost")
        self.style_btn.setCursor(Qt.PointingHandCursor)
        menu = QMenu(self.style_btn)
        for name in STYLE_PRESETS:
            act = menu.addAction(name)
            act.triggered.connect(lambda _, n=name: self._apply_style(n))
        self.style_btn.setMenu(menu)
        head.addWidget(self.style_btn)

        clear_btn = QPushButton("清空")
        clear_btn.setObjectName("ghost")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self._clear_prompt)
        head.addWidget(clear_btn)
        prompt_card.add_layout(head)

        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText(
            "描述你想要的画面，例如：黄昏的海边小镇，暖色阳光，长焦摄影，电影感构图…")
        self.prompt.setMinimumHeight(132)
        self.prompt.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.prompt.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.prompt.setFont(QFont("Microsoft YaHei UI", 10))
        self.prompt.textChanged.connect(self._update_counter)
        prompt_card.add(self.prompt)
        left.addWidget(prompt_card)

        # --- 模型（复选框）
        model_card = Card()
        model_card.add(SectionTitle("模型", "勾选要用的模型：第一个用于生成，失败时自动切换下一个"))
        self.picker = ModelPicker(self, max_height=132)
        self.picker.selectionChanged.connect(self._on_model_pick)
        model_card.add(self.picker)

        model_row = QHBoxLayout()
        model_row.setSpacing(8)
        self.model_hint = QLabel("当前使用：—")
        self.model_hint.setObjectName("hint")
        self.model_hint.setWordWrap(True)
        model_row.addWidget(self.model_hint, 1)
        fetch = QPushButton("拉取模型列表")
        fetch.setObjectName("ghost")
        fetch.setCursor(Qt.PointingHandCursor)
        fetch.clicked.connect(self.ctrl.fetch_models)
        model_row.addWidget(fetch)
        model_card.add_layout(model_row)
        left.addWidget(model_card)

        # --- 参考图（可选，图生图）
        ref_card = Card()
        ref_head = QHBoxLayout()
        ref_head.setSpacing(8)
        ref_head.addWidget(QLabel("参考图"))
        self.ref_hint = ElidedLabel("可选：上传参考图后按图生成")
        self.ref_hint.setObjectName("hint")
        ref_head.addWidget(self.ref_hint, 1)
        self.ref_btn = QPushButton("上传参考图")
        self.ref_btn.setObjectName("ghost")
        self.ref_btn.setCursor(Qt.PointingHandCursor)
        self.ref_btn.clicked.connect(self._pick_reference)
        ref_head.addWidget(self.ref_btn)
        self.ref_clear = QPushButton("清空")
        self.ref_clear.setObjectName("ghost")
        self.ref_clear.setCursor(Qt.PointingHandCursor)
        self.ref_clear.setEnabled(False)
        self.ref_clear.clicked.connect(self._clear_reference)
        ref_head.addWidget(self.ref_clear)
        ref_card.add_layout(ref_head)

        self.ref_strip = ImageDropStrip()
        self.ref_strip.changed.connect(self._on_refs_changed)
        ref_card.add(self.ref_strip)
        left.addWidget(ref_card)

        # --- 参数
        param_card = Card()
        param_card.add(SectionTitle("生成参数", "尺寸、质量与数量会在每次生成时随请求发送"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        self.size_box = self._combo(SIZES)
        grid.addWidget(self._field("尺寸", self.size_box), 0, 0)

        self.quality_box = QComboBox()
        self.quality_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        for value, label in QUALITIES:
            self.quality_box.addItem(label, value)
        grid.addWidget(self._field("质量", self.quality_box), 0, 1)

        self.count_box = QSpinBox()
        self.count_box.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.count_box.setRange(1, 4)
        grid.addWidget(self._field("数量", self.count_box), 1, 0)

        self.format_box = self._combo(FORMATS)
        grid.addWidget(self._field("格式", self.format_box), 1, 1)

        self.transparent = QCheckBox("透明背景（仅 png / webp）")
        grid.addWidget(self.transparent, 2, 0, 1, 2)

        param_card.add_layout(grid)
        left.addWidget(param_card)

        # --- 操作（固定在左栏底部，滚动时也一直看得见）
        action_card = Card(flat=True)
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.gen_btn = QPushButton("生成图片")
        self.gen_btn.setObjectName("primary")
        self.gen_btn.setMinimumHeight(40)
        self.gen_btn.setMinimumWidth(130)
        self.gen_btn.setCursor(Qt.PointingHandCursor)
        self.gen_btn.clicked.connect(self.start_generate)
        action_row.addWidget(self.gen_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setObjectName("ghost")
        self.cancel_btn.setMinimumHeight(40)
        self.cancel_btn.setMinimumWidth(88)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.cancel_generate)
        action_row.addWidget(self.cancel_btn)
        action_row.addStretch(1)

        self.timer_label = QLabel("0.0s")
        self.timer_label.setObjectName("bigTimer")
        self.timer_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.timer_label.setMinimumWidth(74)
        action_row.addWidget(self.timer_label)
        action_card.add_layout(action_row)

        self.stages = StageStepper()
        action_card.add(self.stages)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(5)
        self.progress.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.progress.setVisible(False)
        action_card.add(self.progress)

        self.status = QLabel("就绪")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        action_card.add(self.status)
        left.addStretch(1)

        scroll.setWidget(scroll_host)

        # 左栏容器：上半部分滚动，底部固定操作区
        left_column = QWidget()
        column = QVBoxLayout(left_column)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(12)
        column.addWidget(scroll, 1)
        column.addWidget(action_card)
        split.addWidget(left_column)

        # --- 右侧：预览
        right_host = QWidget()
        right = QVBoxLayout(right_host)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(12)

        preview_card = Card()
        ph = QHBoxLayout()
        ph.setSpacing(8)
        ph.addWidget(QLabel("预览"))
        self.preview_hint = QLabel("")
        self.preview_hint.setObjectName("hint")
        ph.addWidget(self.preview_hint)
        ph.addStretch(1)
        self.open_dir_btn = QPushButton("打开目录")
        self.open_dir_btn.setObjectName("ghost")
        self.open_dir_btn.setCursor(Qt.PointingHandCursor)
        self.open_dir_btn.clicked.connect(self.ctrl.open_output_dir)
        ph.addWidget(self.open_dir_btn)
        self.zoom_btn = QPushButton("放大")
        self.zoom_btn.setObjectName("ghost")
        self.zoom_btn.setEnabled(False)
        self.zoom_btn.setCursor(Qt.PointingHandCursor)
        self.zoom_btn.clicked.connect(self._zoom)
        ph.addWidget(self.zoom_btn)
        preview_card.add_layout(ph)

        self.canvas = ImageCanvas(min_height=320)
        self.canvas.clicked.connect(self._zoom)
        preview_card.add(self.canvas, 1)

        self.thumb_row = QHBoxLayout()
        self.thumb_row.setSpacing(8)
        preview_card.add_layout(self.thumb_row)
        right.addWidget(preview_card, 1)

        split.addWidget(right_host)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 6)
        split.setSizes([520, 620])

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.start_generate)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.prompt.setFocus)

        self.ctrl.modelsChanged.connect(self.set_models)
        self.ctrl.selectionChanged.connect(self._on_selection_changed)

    def _combo(self, items: list[str]) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(items)
        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLength)
        combo.setMinimumContentsLength(8)
        combo.setMinimumWidth(84)
        combo.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        return combo

    def _field(self, label: str, widget: QWidget) -> QWidget:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lbl = QLabel(label)
        lbl.setObjectName("hint")
        lay.addWidget(lbl)
        lay.addWidget(widget)
        return host

    # -------------------------------------------------------------- helpers
    def _update_counter(self):
        text = self.prompt.toPlainText().strip()
        self.counter.setText(f"{len(text)} 字")

    def _clear_prompt(self):
        self.prompt.clear()
        self.prompt.setFocus()

    def _apply_style(self, name: str):
        current = self.prompt.toPlainText().rstrip()
        self.prompt.setPlainText((current + "，" if current else "") + name)
        self.prompt.setFocus()

    def _on_model_pick(self, models: list):
        self.ctrl.set_model_selection(models)
        self._refresh_model_hint()

    def _on_selection_changed(self, models: list):
        self.picker.set_selection(models)
        self._refresh_model_hint()

    def _pick_reference(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择参考图（可多选）", "",
            "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*.*)")
        if not files:
            return
        added = self.ref_strip.add_files(files)
        skipped = len(files) - added
        if added:
            Toast(self, f"已添加 {added} 张参考图", "ok")
        if skipped > 0:
            Toast(self, f"{skipped} 张未添加（最多 6 张，且需为图片）", "warn")

    def _clear_reference(self):
        self.ref_strip.clear()

    def _on_refs_changed(self, paths: list):
        count = len(paths)
        self.ref_clear.setEnabled(count > 0)
        if count:
            self.ref_hint.setText(f"已添加 {count} 张参考图，将随请求一起发送")
        else:
            self.ref_hint.setText("可选：上传参考图后按图生成")

    def _refresh_model_hint(self):
        picked = self.picker.selected_models()
        if picked:
            self.model_hint.setText("当前使用：" + picked[0] +
                                    (f"（备用 {len(picked) - 1} 个）" if len(picked) > 1 else ""))
        else:
            self.model_hint.setText("当前使用：未选择（将使用默认 gpt-image-2）")

    def load_config(self, cfg: dict):
        self.size_box.setCurrentText(cfg.get("size", "4096x4096"))
        quality = cfg.get("quality", "auto")
        idx = self.quality_box.findData(quality)
        self.quality_box.setCurrentIndex(idx if idx >= 0 else 0)
        self.count_box.setValue(int(cfg.get("count", 1)))
        self.format_box.setCurrentText(cfg.get("output_format", "png"))
        self.transparent.setChecked(bool(cfg.get("transparent", False)))
        self._refresh_model_hint()

    def set_models(self, models: list[str]):
        self.picker.set_models(models, self.ctrl.model_selection())
        self._refresh_model_hint()

    def set_prompt(self, text: str):
        self.prompt.setPlainText(text)
        self.prompt.setFocus()

    def _zoom(self):
        path = self.canvas.path()
        if path:
            ImageDialog(path, self).exec_()

    # ------------------------------------------------------------- generate
    def start_generate(self):
        prompt = self.prompt.toPlainText().strip()
        if not prompt:
            Toast(self, "请先填写提示词", "warn")
            self.prompt.setFocus()
            return
        if self.task and self.task.isRunning():
            return
        cfg = self.ctrl.cfg
        picked = self.picker.selected_models()
        models = picked or [cfg.get("image_model") or "gpt-image-2"]
        size = self.size_box.currentText().strip() or "4096x4096"
        refs = self.ref_strip.paths()
        payload = {
            "prompt": prompt,
            "model": models[0],
            "models": models,
            "size": size,
            "quality": self.quality_box.currentData(),
            "count": self.count_box.value(),
            "format": self.format_box.currentText().strip() or "png",
            "transparent": self.transparent.isChecked(),
            "output_dir": cfg.get("output_dir", ""),
            "reference_images": refs,
        }
        self._set_busy(True)
        self._base_status = f"正在准备 {models[0]}"
        self.status.setText(self._base_status)
        self.preview_hint.setText("生成中…")
        ref_note = f"，带 {len(refs)} 张参考图" if refs else ""
        self.canvas.set_loading(True, f"{models[0]} 正在生成 {size}{ref_note}",
                                [f"{h}（{size}）" for h in DRAW_HINTS])
        self._set_stage(STAGE_PREPARE)

        client = self.ctrl.build_client()
        self._client = client
        task = GenerateTask(client, payload)
        task.progress.connect(self._on_progress)
        task.retry.connect(self._on_retry)
        task.succeeded.connect(self._on_success)
        task.failed.connect(self._on_failed)
        task.cancelled.connect(self._on_cancelled)
        task.model_switch.connect(self._on_model_switch)
        task.finished.connect(self._reset_btn)
        self.task = task
        self._started_at = time.time()
        self._tick.start()
        task.start()

    def cancel_generate(self):
        if not (self.task and self.task.isRunning()):
            return
        self._base_status = "正在取消…"
        self.status.setText(self._base_status)
        self.task.cancel()
        self.ctrl.log("用户取消了本次生成")

    def _set_stage(self, stage: int) -> None:
        self._stage = stage
        self.stages.set_stage(stage)
        self._progress_target = STAGE_PROGRESS.get(stage, 0)

    def _set_busy(self, busy: bool):
        self.gen_btn.setEnabled(not busy)
        self.gen_btn.setText("生成中…" if busy else "生成图片")
        self.cancel_btn.setEnabled(busy)
        self.progress.setVisible(busy)
        if not busy:
            self.timer_label.setText("0.0s")
        for widget in (self.size_box, self.quality_box, self.count_box,
                       self.format_box, self.transparent, self.ref_btn, self.ref_clear):
            widget.setEnabled(not busy)

    def _reset_btn(self):
        self._set_busy(False)
        self._tick.stop()

    @safe_slot
    def _on_tick(self):
        if not (self.task and self.task.isRunning()):
            return
        spent = time.time() - self._started_at
        self.timer_label.setText(f"{spent:.1f}s")
        self.status.setText(f"{self._base_status} · {spent:.1f}s")
        # 进度条平滑推进：向目标缓动，绘制阶段再慢慢往上爬，让等待有"活着"的感觉
        self._progress += (self._progress_target - self._progress) * 0.12
        if self._stage == STAGE_DRAW and self._progress < self._progress_target - 2:
            self._progress += 0.35
        self.progress.setValue(int(max(0, min(100, self._progress))))

    @safe_slot
    def _on_progress(self, text: str):
        self._base_status = text
        if "正在连接" in text:
            self._set_stage(STAGE_CONNECT)
        elif "正在绘制" in text:
            self._set_stage(STAGE_DRAW)
        elif "正在保存" in text:
            self._set_stage(STAGE_SAVE)
        if not (self.task and self.task.isRunning()):
            self.status.setText(text)

    @safe_slot
    def _on_retry(self, attempt: int, message: str):
        total = getattr(getattr(self, "_client", None), "max_retries", 5)
        self._base_status = f"第 {attempt}/{total} 次失败：{message.splitlines()[0]} — 正在重试…"
        self.status.setText(self._base_status)
        self._set_stage(STAGE_CONNECT)
        self.ctrl.log(f"[重试 {attempt}/{total}] {message}")

    @safe_slot
    def _on_model_switch(self, failed_model: str, next_model: str):
        self.ctrl.log(f"模型 {failed_model} 不可用，自动切换到 {next_model}")
        Toast(self, f"{failed_model} 不可用，已切换到 {next_model}", "warn")

    @safe_slot
    def _on_success(self, results, elapsed: float):
        self.results = list(results)
        self._base_status = f"完成 · {len(self.results)} 张 · 耗时 {elapsed:.1f}s"
        self.status.setText(self._base_status)
        self.status.setToolTip(f"已保存到 {self.ctrl.cfg.get('output_dir', '')}")
        self._set_stage(STAGE_DONE)
        self._progress = 100
        self.progress.setValue(100)
        self.canvas.set_loading(False)
        self.canvas.flash()
        self.preview_hint.setText("")
        self.timer_label.setText(f"{elapsed:.1f}s")
        self.ctrl.on_images_ready(self.results)
        self._show_thumbs()
        Toast(self, f"生成完成，耗时 {elapsed:.1f}s", "ok")
        self.ctrl.log(f"生成完成：{len(self.results)} 张，耗时 {elapsed:.1f}s，"
                      f"目录 {self.ctrl.cfg.get('output_dir', '')}")

    @safe_slot
    def _on_failed(self, message: str):
        self._base_status = "生成失败"
        self.status.setText(self._base_status)
        self._set_stage(-1)
        self._progress = 0
        self.progress.setValue(0)
        self.canvas.set_loading(False)
        self.preview_hint.setText("")
        self.ctrl.log("生成失败：" + message)
        Toast(self, "生成失败，详情见右下角日志", "error")
        self.ctrl.show_error("生成失败", message)

    @safe_slot
    def _on_cancelled(self):
        self._base_status = "已取消"
        self.status.setText(self._base_status)
        self._set_stage(-1)
        self._progress = 0
        self.progress.setValue(0)
        self.canvas.set_loading(False)
        self.preview_hint.setText("")
        self.ctrl.log("已取消本次生成")

    def _show_thumbs(self):
        while self.thumb_row.count():
            item = self.thumb_row.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for res in self.results:
            btn = QPushButton()
            btn.setObjectName("chip")
            btn.setCheckable(True)
            btn.setFixedSize(74, 74)
            btn.setCursor(Qt.PointingHandCursor)
            icon = self.ctrl.pixmap_for(res.path, 68)
            btn.setIcon(QIcon(icon))
            btn.setIconSize(icon.size())
            btn.setToolTip(f"{res.prompt[:60]}\n{res.width}×{res.height}")
            btn.clicked.connect(lambda _, p=res.path: self._select(p))
            self.thumb_row.addWidget(btn)
        self.thumb_row.addStretch(1)
        if self.results:
            self._select(self.results[0].path)

    def _select(self, path: str):
        self.canvas.set_image(path)
        self.zoom_btn.setEnabled(True)
        self.preview_hint.setText("")
