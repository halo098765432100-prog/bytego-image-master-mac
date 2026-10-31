"""在真实窗口里打开「开发者信息」弹窗并截图（离屏渲染没有字体，截图会缺字）。

用法： py -3.13 tests/shot_dialog_win.py [输出png]
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "shot_dev.png"
HOME = Path(os.environ.get("TEMP", ".")) / "bytego_dialog_home"

LAUNCHER = '''
import sys
sys.path.insert(0, r"{root}")
from PyQt5.QtWidgets import QApplication
from bytego_image_master.ui.main_window import MainWindow
from bytego_image_master.ui.widgets import DeveloperDialog
from bytego_image_master.config import (APP_TITLE, DEVELOPER, DEVELOPER_QQ, VERSION,
                                        endpoint_label, endpoint_url)
app = QApplication(sys.argv)
win = MainWindow()
win.show()
dlg = DeveloperDialog(win, app_title=APP_TITLE, version=VERSION, developer=DEVELOPER,
                      qq=DEVELOPER_QQ, endpoint_label=endpoint_label("cn"),
                      endpoint_url=endpoint_url("cn"))
dlg.show()
dlg.raise_()
sys.exit(app.exec_())
'''

PS = r'''
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class Win {
  public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
$p = Get-Process | Where-Object { $_.MainWindowTitle -like "Bytego*" } | Select-Object -First 1
if (-not $p) { Write-Output "NO_PROCESS"; exit 1 }
$target = [IntPtr]::Zero
$cb = [Win+EnumProc]{
  param($h, $l)
  $procId = 0
  [Win]::GetWindowThreadProcessId($h, [ref]$procId) | Out-Null
  if ($procId -eq $p.Id) {
    $sb = New-Object System.Text.StringBuilder 256
    [Win]::GetWindowText($h, $sb, 256) | Out-Null
    $title = $sb.ToString()
    if ([Win]::IsWindowVisible($h) -and $title -notlike "Bytego*") {
      $script:target = $h
    }
  }
  return $true
}
[Win]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
if ($target -eq [IntPtr]::Zero) { Write-Output "NO_DIALOG"; exit 1 }
[Win]::SetForegroundWindow($target) | Out-Null
Start-Sleep -Milliseconds 700
$r = New-Object Win+RECT
[Win]::GetWindowRect($target, [ref]$r) | Out-Null
$bmp = New-Object System.Drawing.Bitmap(($r.Right - $r.Left), ($r.Bottom - $r.Top))
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
[Win]::PrintWindow($target, $hdc, 2) | Out-Null
$g.ReleaseHdc($hdc); $g.Dispose()
$bmp.Save("{OUT}", [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Write-Output "OK"
'''


def main():
    HOME.mkdir(parents=True, exist_ok=True)
    launcher = HOME / "launcher.py"
    launcher.write_text(LAUNCHER.format(root=str(ROOT)), encoding="utf-8")
    env = dict(os.environ)
    env["BYTEGO_HOME"] = str(HOME)
    env.pop("QT_QPA_PLATFORM", None)
    app = subprocess.Popen([sys.executable, str(launcher)], cwd=str(ROOT), env=env)
    try:
        time.sleep(7)
        script = PS.replace("{OUT}", str(OUT).replace("\\", "\\\\"))
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                             capture_output=True, text=True)
        print(out.stdout.strip(), out.stderr.strip()[:300])
        print(f"screenshot -> {OUT}")
    finally:
        app.terminate()


if __name__ == "__main__":
    main()
