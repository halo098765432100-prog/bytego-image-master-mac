"""验证打包后的 exe：启动、填入提示词、触发生成、检查产物。

用法： py -3.13 tests/verify_exe.py
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PORT = "8841"
EXE = ROOT / "dist" / "Bytego中转站GPT-Image-Grok Image Master.exe"

PS_DRIVE = r'''
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$p = Get-Process | Where-Object { $_.Path -eq "{EXE}" -and $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $p) { Write-Output "NO_PROCESS"; exit 1 }
$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $p.Id)
$win = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)
if (-not $win) { Write-Output "NO_WINDOW"; exit 1 }

$editCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Edit)
$edits = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, $editCond)
$prompt = $null
foreach ($el in $edits) {
  if ($el.Current.BoundingRectangle.Height -ge 100) { $prompt = $el; break }
}
if (-not $prompt) { Write-Output "NO_PROMPT"; exit 1 }

$vp = $null
if (-not $prompt.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$vp)) {
  Write-Output "NO_VALUE_PATTERN"; exit 1
}
$vp.SetValue("{PROMPT}") | Out-Null
Start-Sleep -Milliseconds 400
$tp = $null
if ($prompt.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$tp)) {
  $txt = $tp.DocumentRange.GetText(-1)
  Write-Output ("PROMPT_TEXT='" + $txt + "'")
}

$btnCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Button)
$btns = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, $btnCond)
$target = $null
foreach ($b in $btns) {
  if ($b.Current.Name -like "*{BTN}*") { $target = $b; break }
}
if (-not $target) { Write-Output "NO_BUTTON"; exit 1 }
Write-Output ("BUTTON='" + $target.Current.Name + "' enabled=" + $target.Current.IsEnabled)
$ip = $null
if ($target.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$ip)) {
  $ip.Invoke()
  Write-Output "INVOKED"
} else {
  Write-Output "NO_INVOKE"
}
'''

PS_CAPTURE = r'''
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
$p = Get-Process | Where-Object { $_.Path -eq "{EXE}" -and $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $p) { Write-Output "NO_WINDOW"; exit 1 }
$h = $p.MainWindowHandle
[Win]::ShowWindow($h, 3) | Out-Null
[Win]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 700
$r = New-Object Win+RECT
[Win]::GetWindowRect($h, [ref]$r) | Out-Null
$bmp = New-Object System.Drawing.Bitmap(($r.Right - $r.Left), ($r.Bottom - $r.Top))
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
[Win]::PrintWindow($h, $hdc, 2) | Out-Null
$g.ReleaseHdc($hdc); $g.Dispose()
$bmp.Save("{OUT}", [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output "OK"
'''


def seed(home: Path, out_dir: Path):
    home.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    (home / "history.json").write_text("[]", encoding="utf-8")
    (home / "config.json").write_text(json.dumps({
        "endpoint": "global", "api_key": "sk-demo-local-mock",
        "image_model": "gpt-image-2", "chat_model": "gpt-4o", "size": "4096x4096",
        "quality": "auto", "count": 1, "output_format": "png", "transparent": False,
        "max_retries": 5, "timeout": 1000, "auto_approve": False,
        "output_dir": str(out_dir), "allow_command": True, "allow_write": True,
        "allow_open": True, "allow_generate": True}, ensure_ascii=False), encoding="utf-8")


def capture(path: Path):
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    PS_CAPTURE.replace("{OUT}", str(path).replace("\\", "\\\\"))
                                    .replace("{EXE}", str(EXE))],
                   capture_output=True, text=True)


def main() -> int:
    if not EXE.exists():
        print("未找到 exe:", EXE)
        return 1
    home = Path(os.environ.get("TEMP", ".")) / "bytego_exe_test"
    out_dir = home / "out"
    if out_dir.exists():
        for f in out_dir.glob("*"):
            f.unlink()
    seed(home, out_dir)

    server = subprocess.Popen([sys.executable, str(ROOT / "tests" / "mock_server.py"), PORT],
                              cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    env = dict(os.environ)
    env["BYTEGO_HOME"] = str(home)
    env["BYTEGO_BASE_URL"] = f"http://127.0.0.1:{PORT}/v1"
    env.pop("QT_QPA_PLATFORM", None)
    t0 = time.time()
    app = subprocess.Popen([str(EXE)], cwd=str(ROOT), env=env)
    failures = []
    try:
        time.sleep(9)
        print(f"启动耗时（含解包）：{time.time() - t0:.1f}s")

        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              PS_DRIVE.replace("{PROMPT}", "mock exe e2e prompt")
                                       .replace("{BTN}", "生成图片")
                                       .replace("{EXE}", str(EXE))],
                             capture_output=True, text=True)
        print("驱动：", out.stdout.strip().replace("\n", " | "))
        if out.stderr.strip():
            print("STDERR:", out.stderr.strip()[:300])

        typed_shot = ROOT / "shot_exe_typed.png"
        capture(typed_shot)
        print("输入后截图：", typed_shot)

        deadline = time.time() + 45
        produced = []
        while time.time() < deadline:
            produced = list(out_dir.glob("*.png"))
            if produced:
                break
            time.sleep(1)

        shot = ROOT / "shot_exe.png"
        capture(shot)

        print("输出目录文件：", [p.name for p in produced])
        if produced:
            data = produced[0].read_bytes()
            print("图片大小：", len(data), "字节，PNG 头：", data[:4] == b"\x89PNG")
            if len(data) < 1000 or data[:4] != b"\x89PNG":
                failures.append("生成的图片无效")
        else:
            failures.append("exe 未产出图片")
        print("截图：", shot)
    finally:
        app.terminate()
        server.terminate()

    if failures:
        print("失败：", "、".join(failures))
        return 1
    print("exe 端到端验证通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
