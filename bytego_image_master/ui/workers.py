import time

from PyQt5.QtCore import QThread, pyqtSignal


class GenerateTask(QThread):
    """在后台线程里跑图片生成，避免界面卡死。

    payload["models"] 为按优先级排列的模型列表：第一个失败会自动切下一个。
    """

    progress = pyqtSignal(str)
    retry = pyqtSignal(int, str)
    succeeded = pyqtSignal(object, float)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()
    model_switch = pyqtSignal(str, str)

    def __init__(self, client, payload: dict, parent=None):
        super().__init__(parent)
        self.client = client
        self.payload = payload
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        try:
            self.client.cancel()
        except Exception:
            pass

    def run(self):
        payload = dict(self.payload)
        models = [m for m in (payload.get("models") or []) if m]
        if not models:
            models = [payload.get("model", "gpt-image-2")]
        started = time.time()
        last_error = ""
        for index, model in enumerate(models):
            if self._cancelled:
                self.cancelled.emit()
                return
            if index > 0:
                self.model_switch.emit(models[index - 1], model)
            body = dict(payload)
            body["model"] = model
            try:
                results = self.client.generate_image(
                    prompt=payload["prompt"],
                    model=model,
                    size=payload["size"],
                    quality=payload["quality"],
                    count=payload["count"],
                    output_format=payload["format"],
                    transparent=payload.get("transparent", False),
                    output_dir=payload.get("output_dir", ""),
                    on_retry=lambda attempt, err: self.retry.emit(attempt, err.display()),
                    on_progress=lambda text: self.progress.emit(text),
                    reference_images=payload.get("reference_images") or [],
                )
            except Exception as exc:
                if self._cancelled:
                    self.cancelled.emit()
                    return
                last_error = str(exc)
                if index + 1 < len(models):
                    self.progress.emit(f"模型 {model} 不可用，切换到 {models[index + 1]} …")
                    continue
                break
            if self._cancelled:
                self.cancelled.emit()
                return
            self.succeeded.emit(results, time.time() - started)
            return
        if len(models) > 1:
            names = "、".join(models)
            self.failed.emit(f"已依次尝试 {len(models)} 个模型（{names}）仍失败：\n{last_error}")
        else:
            self.failed.emit(last_error or "生成失败")


class FunctionTask(QThread):
    """跑一个普通函数并把结果送回界面线程。"""

    done = pyqtSignal(object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            result = self.fn()
        except Exception as exc:
            result = {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}
        self.done.emit(result)


class AgentTask(QThread):
    """后台线程里跑 Agent 对话循环。"""

    event = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, agent, user_input: str, history: list, parent=None):
        super().__init__(parent)
        self.agent = agent
        self.user_input = user_input
        self.history = list(history)

    def run(self):
        try:
            self.agent.run(self.user_input, self.history,
                           on_event=lambda e: self.event.emit(e),
                           on_retry=lambda attempt, err: self.event.emit(
                               {"type": "retry", "attempt": attempt, "message": err.display()}))
        except Exception as exc:
            self.failed.emit(str(exc))
