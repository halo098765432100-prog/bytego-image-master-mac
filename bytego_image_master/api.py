import base64
import json
import mimetypes
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Optional

import requests

from .config import USER_AGENT

FRIENDLY_HINTS = {
    400: "请求参数不被接口接受，请检查模型名/尺寸/提示词",
    401: "API Key 无效或未填写",
    403: "没有访问权限，请检查 Key 权限或区域限制",
    404: "接口不存在，请检查 Base URL 是否包含 /v1",
    408: "服务端等待超时",
    409: "请求冲突，请稍后重试",
    413: "请求内容过大",
    422: "参数校验失败，请检查填写内容",
    429: "请求过于频繁或额度不足",
    500: "服务端内部错误",
    502: "网关错误，服务可能暂时不可用",
    503: "服务繁忙",
    504: "网关超时",
}


class ApiError(Exception):
    def __init__(self, message: str, status: Optional[int] = None, detail: str = "", attempt: int = 0):
        super().__init__(message)
        self.message = message
        self.status = status
        self.detail = detail
        self.attempt = attempt

    def display(self) -> str:
        head = f"[HTTP {self.status}] " if self.status else ""
        body = f"{self.message}"
        if self.detail and self.detail not in self.message:
            body = f"{body}\n{self.detail}"
        hint = FRIENDLY_HINTS.get(self.status or 0)
        if hint:
            body = f"{body}\n提示：{hint}"
        return f"{head}{body}"


@dataclass
class ImageResult:
    path: str
    prompt: str
    size: str
    quality: str
    model: str
    fmt: str
    created: int = field(default_factory=lambda: int(time.time()))
    width: int = 0
    height: int = 0
    bytes: int = 0

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "prompt": self.prompt,
            "size": self.size,
            "quality": self.quality,
            "model": self.model,
            "fmt": self.fmt,
            "created": self.created,
            "width": self.width,
            "height": self.height,
            "bytes": self.bytes,
        }


class ApiClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 1000, max_retries: int = 5):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.timeout = int(timeout or 1000)
        self.max_retries = max(1, int(max_retries or 1))
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self.session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})
        adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=16, max_retries=0)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    # ---------------------------------------------------------------- cancel
    def cancel(self) -> None:
        """中断进行中的请求：关闭连接池 + 置位取消标记。"""
        self._cancel.set()
        with self._lock:
            try:
                self.session.close()
            except Exception:
                pass

    def reset_cancel(self) -> None:
        self._cancel.clear()
        with self._lock:
            self.session = self._build_session()

    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    # ---------------------------------------------------------------- helpers
    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        if not self.base_url:
            raise ApiError("未配置 API 地址，请到「设置」选择中转站线路")
        if not self.base_url.lower().startswith(("http://", "https://")):
            self.base_url = "https://" + self.base_url
        return f"{self.base_url}/{path.lstrip('/')}"

    def _host(self) -> str:
        try:
            return self.base_url.split("//", 1)[-1].split("/", 1)[0]
        except Exception:
            return self.base_url

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _extract_error(self, resp: requests.Response) -> tuple[str, str]:
        raw = ""
        try:
            raw = resp.text or ""
        except Exception:
            raw = ""
        detail = ""
        try:
            data = resp.json()
        except ValueError:
            data = None
        message = ""
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                message = str(err.get("message") or err.get("detail") or "")
                extra = [err.get("type"), err.get("code")]
                extra = [str(e) for e in extra if e]
                if extra:
                    detail = " · ".join(extra)
            elif isinstance(err, str):
                message = err
            elif data.get("message"):
                message = str(data["message"])
            elif data.get("detail"):
                message = str(data["detail"])
            else:
                message = json.dumps(data, ensure_ascii=False)[:600]
        elif raw:
            message = raw[:600]
        if not message:
            message = f"请求失败（HTTP {resp.status_code}）"
        return message, detail

    def _sleep_backoff(self, attempt: int) -> float:
        return min(1.2 * attempt, 6.0)

    def _retry(self, action: Callable[[int], object],
               on_attempt_fail: Optional[Callable[[int, ApiError], None]] = None) -> object:
        last: Optional[ApiError] = None
        for attempt in range(1, self.max_retries + 1):
            if self._cancel.is_set():
                raise ApiError("已取消本次请求")
            try:
                return action(attempt)
            except ApiError as exc:
                exc.attempt = attempt
                last = exc
                if self._cancel.is_set():
                    break
                if attempt >= self.max_retries:
                    break
                if on_attempt_fail:
                    on_attempt_fail(attempt, exc)
                # 可被取消事件立刻唤醒
                if self._cancel.wait(self._sleep_backoff(attempt)):
                    break
        if last is None:
            last = ApiError("已取消本次请求")
        raise last

    def _read_json(self, resp: requests.Response) -> dict:
        """分段读取响应体，读取途中也能响应取消。"""
        try:
            chunks = []
            for chunk in resp.iter_content(65536):
                if self._cancel.is_set():
                    raise ApiError("已取消本次请求")
                if chunk:
                    chunks.append(chunk)
            raw = b"".join(chunks)
        except ApiError:
            raise
        except requests.RequestException as exc:
            raise ApiError(f"网络连接失败：{exc.__class__.__name__}", detail=str(exc)) from exc
        try:
            return json.loads(raw.decode("utf-8", "replace") or "{}")
        except ValueError as exc:
            raise ApiError("接口返回的不是合法 JSON", detail=str(exc)) from exc

    # ---------------------------------------------------------------- images
    def generate_image(self, prompt: str, model: str, size: str, quality: str,
                       count: int = 1, output_format: str = "png",
                       transparent: bool = False, output_dir: str = "",
                       on_retry: Optional[Callable[[int, ApiError], None]] = None,
                       on_progress: Optional[Callable[[str], None]] = None,
                       reference_images: Optional[list[str]] = None) -> list[ImageResult]:
        body = {
            "model": model,
            "prompt": prompt,
            "n": int(count),
            "size": size,
            "output_format": output_format,
        }
        if quality:
            body["quality"] = quality
        if transparent and output_format in ("png", "webp"):
            body["background"] = "transparent"

        refs = [str(p) for p in (reference_images or []) if p and os.path.exists(p)]
        form = {k: str(v) for k, v in body.items()}
        use_refs = bool(refs)

        def action(attempt: int):
            nonlocal use_refs
            resp = None
            if on_progress:
                on_progress(f"正在连接 {self._host()} …")
            handles: list = []
            try:
                if use_refs:
                    field = "image" if len(refs) == 1 else "image[]"
                    files = []
                    for path in refs:
                        handle = open(path, "rb")
                        handles.append(handle)
                        ctype = mimetypes.guess_type(path)[0] or "image/png"
                        files.append((field, (os.path.basename(path), handle, ctype)))
                    headers = {}
                    if self.api_key:
                        headers["Authorization"] = f"Bearer {self.api_key}"
                    resp = self.session.post(self._url("/images/edits"), data=form, files=files,
                                             headers=headers, timeout=self.timeout, stream=True)
                else:
                    resp = self.session.post(self._url("/images/generations"), json=body,
                                             headers=self._headers(), timeout=self.timeout,
                                             stream=True)
            except requests.Timeout as exc:
                raise ApiError(f"请求超时（>{self.timeout}s），接口响应过慢", detail=str(exc)) from exc
            except requests.RequestException as exc:
                raise ApiError(f"网络连接失败：{exc.__class__.__name__}", detail=str(exc)) from exc
            finally:
                for handle in handles:
                    try:
                        handle.close()
                    except Exception:
                        pass
            try:
                if resp.status_code >= 400:
                    # 该线路没有 images/edits：退回纯文生图，并明确告知用户
                    if use_refs and resp.status_code in (404, 405, 501):
                        use_refs = False
                        if on_progress:
                            on_progress("当前线路不支持参考图上传，已改为纯文本生成")
                        try:
                            resp.close()
                        except Exception:
                            pass
                        return action(attempt)
                    msg, detail = self._extract_error(resp)
                    raise ApiError(msg, status=resp.status_code, detail=detail)
                if on_progress:
                    on_progress(f"{model} 正在绘制 {size} …")
                data = self._read_json(resp)
            finally:
                try:
                    resp.close()
                except Exception:
                    pass
            if not isinstance(data, dict) or "data" not in data:
                raise ApiError("接口返回缺少 data 字段",
                               detail=json.dumps(data, ensure_ascii=False)[:400])
            return data

        data = self._retry(action, on_retry)
        items = data.get("data") or []
        if not items:
            raise ApiError("接口返回了空的图片列表", detail=json.dumps(data, ensure_ascii=False)[:400])

        out_dir = Path(output_dir) if output_dir else Path.cwd()
        out_dir.mkdir(parents=True, exist_ok=True)
        results: list[ImageResult] = []
        for idx, item in enumerate(items):
            if self._cancel.is_set():
                raise ApiError("已取消本次请求")
            if on_progress:
                on_progress(f"正在保存第 {idx + 1}/{len(items)} 张…")
            b64 = item.get("b64_json") or item.get("b64") or ""
            url = item.get("url") or ""
            if not b64 and url:
                b64 = self._download_b64(url, on_retry)
            if not b64:
                raise ApiError("图片数据缺少 b64_json 与 url 字段")
            raw = base64.b64decode(b64 + "=" * (-len(b64) % 4))
            ext = (output_format or "png").lower()
            ext = "jpg" if ext == "jpeg" else ext
            stamp = time.strftime("%Y%m%d_%H%M%S")
            fname = f"bytego_{stamp}_{int(time.time() * 1000) % 10000}.{ext}"
            path = out_dir / fname
            path.write_bytes(raw)
            width = height = 0
            try:
                from PIL import Image
                with Image.open(path) as im:
                    width, height = im.size
            except Exception:
                pass
            results.append(ImageResult(path=str(path), prompt=prompt, size=size, quality=quality,
                                      model=model, fmt=ext, width=width, height=height,
                                      bytes=len(raw)))
        return results

    def _download_b64(self, url: str, on_retry=None) -> str:
        def action(attempt: int) -> str:
            try:
                resp = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as exc:
                raise ApiError(f"下载图片失败：{exc.__class__.__name__}", detail=str(exc)) from exc
            if resp.status_code >= 400:
                msg, detail = self._extract_error(resp)
                raise ApiError(msg, status=resp.status_code, detail=detail)
            return base64.b64encode(resp.content).decode("ascii")
        return self._retry(action, on_retry)

    def list_models(self) -> list[str]:
        def action(attempt: int) -> list[str]:
            try:
                resp = self.session.get(self._url("/models"), headers=self._headers(), timeout=30)
            except requests.RequestException as exc:
                raise ApiError(f"网络连接失败：{exc.__class__.__name__}", detail=str(exc)) from exc
            if resp.status_code >= 400:
                msg, detail = self._extract_error(resp)
                raise ApiError(msg, status=resp.status_code, detail=detail)
            data = resp.json()
            items = data.get("data") or []
            return [str(i.get("id")) for i in items if i.get("id")]
        return self._retry(action)

    # ---------------------------------------------------------------- chat
    def chat_stream(self, messages: list, tools: Optional[list] = None,
                    model: str = "", temperature: Optional[float] = None,
                    on_retry=None) -> Iterator[dict]:
        body: dict = {"model": model, "messages": messages, "stream": True}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if temperature is not None:
            body["temperature"] = temperature

        def action(attempt: int):
            try:
                resp = self.session.post(self._url("/chat/completions"), json=body,
                                         headers=self._headers(), timeout=(30, self.timeout),
                                         stream=True)
            except requests.Timeout as exc:
                raise ApiError(f"对话请求超时（>{self.timeout}s）", detail=str(exc)) from exc
            except requests.RequestException as exc:
                raise ApiError(f"网络连接失败：{exc.__class__.__name__}", detail=str(exc)) from exc
            if resp.status_code >= 400:
                msg, detail = self._extract_error(resp)
                raise ApiError(msg, status=resp.status_code, detail=detail)
            return resp

        resp = self._retry(action, on_retry)
        tool_acc: dict[int, dict] = {}
        try:
            for raw_line in resp.iter_lines(decode_unicode=True):
                if raw_line is None:
                    continue
                line = raw_line.strip()
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except ValueError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                text = delta.get("content")
                if text:
                    yield {"type": "text", "text": text}
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    slot = tool_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] += fn["name"]
                    if fn.get("arguments"):
                        slot["arguments"] += fn["arguments"]
        except requests.RequestException as exc:
            raise ApiError("对话流中断", detail=str(exc)) from exc
        finally:
            resp.close()
        calls = []
        for idx in sorted(tool_acc):
            slot = tool_acc[idx]
            if slot.get("name"):
                calls.append(slot)
        if calls:
            yield {"type": "tool_calls", "calls": calls}
        yield {"type": "done"}

    def chat_once(self, messages: list, model: str = "", tools: Optional[list] = None) -> dict:
        body: dict = {"model": model, "messages": messages}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        try:
            resp = self.session.post(self._url("/chat/completions"), json=body,
                                     headers=self._headers(), timeout=self.timeout)
        except requests.RequestException as exc:
            raise ApiError(f"网络连接失败：{exc.__class__.__name__}", detail=str(exc)) from exc
        if resp.status_code >= 400:
            msg, detail = self._extract_error(resp)
            raise ApiError(msg, status=resp.status_code, detail=detail)
        return resp.json()
