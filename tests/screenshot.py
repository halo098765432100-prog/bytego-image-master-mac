"""启动真实界面并截图，用于人工检查视觉效果。

用法： py -3.13 tests/screenshot.py [输出png] [页码 0生成/1作品库/2Agent/3设置]
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.mock_server import make_png  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "shot.png"
PAGE = int(sys.argv[2]) if len(sys.argv) > 2 else 0
PORT = "8823"

PS_SCRIPT = r'''
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
$p = Get-Process | Where-Object { $_.MainWindowTitle -like "Bytego*" } | Select-Object -First 1
if (-not $p) { Write-Output "NO_WINDOW"; exit 1 }
$h = $p.MainWindowHandle
[Win]::ShowWindow($h, 3) | Out-Null
[Win]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 800
$r = New-Object Win+RECT
[Win]::GetWindowRect($h, [ref]$r) | Out-Null
$bmp = New-Object System.Drawing.Bitmap(($r.Right - $r.Left), ($r.Bottom - $r.Top))
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
[Win]::PrintWindow($h, $hdc, 2) | Out-Null
$g.ReleaseHdc($hdc)
$g.Dispose()
$bmp.Save("{OUT}", [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output "OK"
'''

LAUNCHER = '''
import sys
sys.path.insert(0, r"{root}")
from PyQt5.QtWidgets import QApplication
from bytego_image_master.ui.main_window import MainWindow
app = QApplication(sys.argv)
win = MainWindow()
win.switch_page({page})
{extra}
win.show()
sys.exit(app.exec_())
'''

AGENT_EXTRA = '''
page = win.page_agent
page._add_user("查一下本机的公网 IP，然后把结果存到 D:/ip.txt，再生成一张赛博朋克风格的城市图")
page._add_assistant().setText("好的，我先查一下公网 IP。")
page._add_tool({"name": "run_command", "args": {"command": "curl -s ifconfig.me"},
                "ok": True, "result": "退出码：0\\n标准输出：\\n203.0.113.42"})
page._add_assistant().setText("公网 IP 是 203.0.113.42，已写入 D:/ip.txt。图片也已生成到输出目录。")
'''

GENERATE_EXTRA = '''
win.set_models([
    "gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst", "gpt-image-2.5-halo",
    "gpt-image-1.5", "gpt-image-1", "gpt-image-1-mini", "dall-e-3", "dall-e-2",
    "chatgpt-image-latest", "meta/llama-3.3-70b-instruct", "qwen-image-max",
])
win.set_model_selection(["gpt-image-2.5-sunburst", "gpt-image-2"])
win.page_generate.set_models(win.models)
win.page_generate.set_prompt(
    "一个14岁中国帅气男孩穿着厚卫衣、篮球鞋走在荒郊野岭的小路上，"
    "黄昏侧逆光，胶片颗粒感，电影感构图，细节到位")
'''
BUSY_EXTRA = GENERATE_EXTRA + '''
win.page_generate.set_prompt("slow 一只坐在窗台上的橘猫，柔和自然光")
win.page_generate.start_generate()
'''

SETTINGS_BOTTOM_EXTRA = '''
from PyQt5.QtWidgets import QScrollArea
for area in win.page_settings.findChildren(QScrollArea):
    area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
'''


def seed(home: Path, out_dir: Path):
    home.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    history = []
    samples = [("黄昏的海边小镇，暖色阳光，长焦摄影", 512, 512), ("赛博朋克城市夜景，霓虹反射", 640, 384),
               ("极简几何海报，瑞士风格", 512, 512), ("水彩风格的森林小屋", 640, 384),
               ("电影感人像，柔和侧光", 512, 512), ("科幻太空站内部", 640, 384)]
    for i, (prompt, w, h) in enumerate(samples):
        path = out_dir / f"sample_{i + 1}.png"
        path.write_bytes(make_png(f"#{i + 1}", (w, h)))
        history.append({"path": str(path), "prompt": prompt, "size": f"{w}x{h}",
                        "quality": "auto", "model": "gpt-image-2", "fmt": "png",
                        "created": int(time.time()) - i * 3600, "width": w, "height": h,
                        "bytes": path.stat().st_size})
    (home / "history.json").write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
    (home / "config.json").write_text(json.dumps({
        "endpoint": "global", "api_key": "sk-demo-local-mock",
        "image_model": "gpt-image-2", "chat_model": "gpt-4o", "size": "4096x4096",
        "quality": "auto", "count": 1, "output_format": "png", "transparent": False,
        "max_retries": 5, "timeout": 1000, "auto_approve": False,
        "output_dir": str(out_dir), "allow_command": True, "allow_write": True,
        "allow_open": True, "allow_generate": True}, ensure_ascii=False), encoding="utf-8")


def main():
    home = Path(os.environ.get("TEMP", ".")) / "bytego_shot_home"
    out_dir = home / "out"
    seed(home, out_dir)

    server = subprocess.Popen([sys.executable, str(ROOT / "tests" / "mock_server.py"), PORT],
                              cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    launcher = home / "launcher.py"
    extra = ""
    if PAGE == 2:
        extra = AGENT_EXTRA
    elif PAGE == 4:
        extra = BUSY_EXTRA
    elif PAGE == 0:
        extra = GENERATE_EXTRA
    elif PAGE == 5:
        extra = SETTINGS_BOTTOM_EXTRA
    if PAGE in (0, 4):
        ref = (out_dir / "sample_1.png").as_posix()
        extra += f'\nwin.page_generate.ref_strip.add_files([r"{ref}"])'
    launcher.write_text(LAUNCHER.format(root=str(ROOT), page=3 if PAGE == 5 else (0 if PAGE == 4 else PAGE),
                                        extra=extra), encoding="utf-8")
    env = dict(os.environ)
    env["BYTEGO_HOME"] = str(home)
    env["BYTEGO_BASE_URL"] = f"http://127.0.0.1:{PORT}/v1"
    env.pop("QT_QPA_PLATFORM", None)
    app = subprocess.Popen([sys.executable, str(launcher)], cwd=str(ROOT), env=env)
    try:
        time.sleep(7 if PAGE != 4 else 3)
        ps = PS_SCRIPT.replace("{OUT}", str(OUT).replace("\\", "\\\\"))
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)
        print(f"screenshot -> {OUT}")
    finally:
        app.terminate()
        server.terminate()


if __name__ == "__main__":
    main()
