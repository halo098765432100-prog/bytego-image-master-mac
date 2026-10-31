import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from .platforms import open_in_file_manager, shell_argv, shell_tool_label

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "在用户本机执行一条命令行（Windows 默认 PowerShell，macOS 用 zsh）。用于查 IP、启动服务、跑脚本、查看系统信息等。命令可能改变系统状态，执行前会向用户确认。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的命令行内容"},
                    "cwd": {"type": "string", "description": "工作目录，默认为用户主目录"},
                    "shell": {"type": "string", "enum": ["powershell", "cmd"], "description": "使用的 shell（仅 Windows 生效，macOS/Linux 固定用系统 shell），默认 powershell"},
                    "timeout": {"type": "integer", "description": "超时秒数，默认 60，最大 300"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取本机文本文件内容，返回前若干字符。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件绝对路径"},
                    "max_chars": {"type": "integer", "description": "最多返回字符数，默认 4000，最大 20000"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "把文本写入本机文件（会覆盖同名文件）。写入前会向用户确认。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件绝对路径"},
                    "content": {"type": "string", "description": "要写入的文本内容"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "列出本机某个目录下的文件与子目录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录绝对路径，默认为用户主目录"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_path",
            "description": "用系统默认程序打开文件或目录（Windows 资源管理器 / macOS 访达）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件或目录绝对路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "调用 Bytego 中转站的图像模型生成图片，结果会进入作品库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "图片提示词"},
                    "size": {"type": "string", "description": "尺寸，如 1024x1024"},
                    "quality": {"type": "string", "description": "质量 low/medium/high/auto"},
                    "count": {"type": "integer", "description": "生成数量，默认 1"},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_history",
            "description": "查看最近生成过的图片记录（提示词、路径、时间）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "返回条数，默认 10"},
                },
                "required": [],
            },
        },
    },
]

TOOL_NAMES = [t["function"]["name"] for t in TOOLS]

RISK = {
    "run_command": "confirm",
    "write_file": "confirm",
    "open_path": "confirm",
    "read_file": "safe",
    "list_directory": "safe",
    "list_history": "safe",
    "generate_image": "app",
}

PERMISSION_KEY = {
    "run_command": "allow_command",
    "write_file": "allow_write",
    "open_path": "allow_open",
    "generate_image": "allow_generate",
}


class ToolRunner:
    def __init__(self, cfg: dict,
                 confirm: Optional[Callable[[str, dict], bool]] = None,
                 generate_fn: Optional[Callable[[str, str, str, int], list]] = None,
                 history_fn: Optional[Callable[[int], list]] = None):
        self.cfg = cfg or {}
        self.confirm = confirm
        self.generate_fn = generate_fn
        self.history_fn = history_fn

    def execute(self, name: str, args: dict) -> tuple[bool, str]:
        args = args if isinstance(args, dict) else {}
        handler = {
            "run_command": self._run_command,
            "read_file": self._read_file,
            "write_file": self._write_file,
            "list_directory": self._list_directory,
            "open_path": self._open_path,
            "generate_image": self._generate_image,
            "list_history": self._list_history,
        }.get(name)
        if handler is None:
            return False, f"未知工具：{name}"
        perm = PERMISSION_KEY.get(name)
        if perm and not self.cfg.get(perm, True):
            return False, f"工具 {name} 已被用户在设置中禁用"
        if RISK.get(name) == "confirm" and self.confirm:
            ok = self.confirm(name, args)
            if not ok:
                return False, "用户拒绝了该操作"
        try:
            return True, handler(args)
        except Exception as exc:
            return False, f"执行失败：{exc.__class__.__name__}: {exc}"

    # ------------------------------------------------------------- handlers
    def _run_command(self, args: dict) -> str:
        command = str(args.get("command") or "").strip()
        if not command:
            return "错误：command 为空"
        cwd = str(args.get("cwd") or str(Path.home()))
        shell = str(args.get("shell") or "").lower()
        timeout = max(5, min(int(args.get("timeout") or 60), 300))
        if not Path(cwd).exists():
            cwd = str(Path.home())
        argv = shell_argv(command, shell)
        try:
            proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                                  timeout=timeout, encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return f"命令执行超时（>{timeout}s）"
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        parts = [f"退出码：{proc.returncode}"]
        if out:
            parts.append("标准输出：\n" + out[:4000])
        if err:
            parts.append("错误输出：\n" + err[:2000])
        if len(parts) == 1:
            parts.append("（无输出）")
        return "\n".join(parts)

    def _read_file(self, args: dict) -> str:
        path = Path(str(args.get("path") or "")).expanduser()
        max_chars = max(100, min(int(args.get("max_chars") or 4000), 20000))
        if not path.exists():
            return f"错误：文件不存在 -> {path}"
        if not path.is_file():
            return f"错误：不是文件 -> {path}"
        data = path.read_bytes()
        if b"\x00" in data[:2048]:
            return "错误：这是二进制文件，无法作为文本读取"
        text = data.decode("utf-8", errors="replace")
        head = f"文件：{path}（{len(data)} 字节）\n---\n"
        return head + text[:max_chars] + ("\n...（内容已截断）" if len(text) > max_chars else "")

    def _write_file(self, args: dict) -> str:
        path = Path(str(args.get("path") or "")).expanduser()
        content = args.get("content")
        if not isinstance(content, str):
            return "错误：content 必须是字符串"
        path.parent.mkdir(parents=True, exist_ok=True)
        existed = path.exists()
        path.write_text(content, encoding="utf-8")
        verb = "覆盖" if existed else "创建"
        return f"已{verb}文件：{path}（{len(content.encode('utf-8'))} 字节）"

    def _list_directory(self, args: dict) -> str:
        path = Path(str(args.get("path") or str(Path.home()))).expanduser()
        if not path.exists():
            return f"错误：目录不存在 -> {path}"
        if not path.is_dir():
            return f"错误：不是目录 -> {path}"
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        lines = [f"目录：{path}（共 {len(entries)} 项）"]
        for item in entries[:200]:
            try:
                size = item.stat().st_size
            except OSError:
                size = 0
            kind = "DIR " if item.is_dir() else "FILE"
            lines.append(f"{kind}  {size:>12,}  {item.name}")
        if len(entries) > 200:
            lines.append(f"...（另有 {len(entries) - 200} 项未显示）")
        return "\n".join(lines)

    def _open_path(self, args: dict) -> str:
        path = Path(str(args.get("path") or str(Path.home()))).expanduser()
        if not path.exists():
            return f"错误：路径不存在 -> {path}"
        try:
            open_in_file_manager(path)  # noqa: S606 - 用户确认后由系统默认程序打开
        except Exception as exc:
            return f"打开失败：{exc}"
        return f"已打开：{path}"

    def _generate_image(self, args: dict) -> str:
        if not self.generate_fn:
            return "错误：图像生成功能不可用"
        prompt = str(args.get("prompt") or "").strip()
        if not prompt:
            return "错误：prompt 为空"
        size = str(args.get("size") or self.cfg.get("size") or "1024x1024")
        quality = str(args.get("quality") or self.cfg.get("quality") or "auto")
        count = max(1, min(int(args.get("count") or 1), 4))
        results = self.generate_fn(prompt, size, quality, count)
        if not results:
            return "错误：没有生成任何图片"
        lines = [f"已生成 {len(results)} 张图片："]
        for r in results:
            lines.append(f"- {getattr(r, 'path', r)}（{getattr(r, 'width', 0)}x{getattr(r, 'height', 0)}）")
        return "\n".join(lines)

    def _list_history(self, args: dict) -> str:
        if not self.history_fn:
            return "错误：历史记录不可用"
        limit = max(1, min(int(args.get("limit") or 10), 50))
        items = self.history_fn(limit)
        if not items:
            return "暂无生成记录"
        lines = [f"最近 {len(items)} 条生成记录："]
        for i, it in enumerate(items, 1):
            prompt = str(it.get("prompt", ""))[:80]
            lines.append(f"{i}. [{it.get('size', '')}] {prompt}\n   {it.get('path', '')}")
        return "\n".join(lines)
