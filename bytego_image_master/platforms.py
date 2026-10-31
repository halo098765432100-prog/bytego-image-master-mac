"""平台差异的小工具：Windows / macOS / Linux 都收敛到这里。

注意：平台判断在调用时读取 sys.platform（而不是模块常量），
方便测试里用 mock.patch("sys.platform", "darwin") 验证各分支。
"""
import os
import subprocess
import sys
from pathlib import Path


def open_in_file_manager(path) -> None:
    """用系统文件管理器打开目录/文件：Windows 资源管理器、macOS 访达、Linux xdg-open。"""
    p = Path(path)
    if sys.platform == "win32":
        os.startfile(str(p))  # noqa: S606 - 用户触发的打开操作
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", str(p)])  # noqa: S606


def shell_argv(command: str, shell: str = "") -> list:
    """把 Agent 的 run_command 参数翻译成当前平台的命令行。

    Windows：powershell（默认）/ cmd；macOS：zsh；Linux：bash。
    """
    if sys.platform == "win32":
        if shell.lower() == "cmd":
            return ["cmd.exe", "/c", command]
        return ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]
    if sys.platform == "darwin":
        return ["/bin/zsh", "-lc", command]
    return ["/bin/bash", "-lc", command]


def shell_tool_label() -> str:
    """给 Agent 工具描述/系统提示词用的 shell 名称。"""
    if sys.platform == "win32":
        return "PowerShell"
    if sys.platform == "darwin":
        return "zsh"
    return "bash"
