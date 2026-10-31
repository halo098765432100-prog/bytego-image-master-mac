"""验证 Windows 安装包：静默安装 → 跑一次生成 → 静默卸载 → 检查清理。

用法： py -3.13 tests/verify_installer.py
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PORT = "8853"
SETUP = ROOT / "dist" / "Bytego中转站GPT-Image-Grok Image Master-Setup-1.1.0.exe"
EXE_NAME = "Bytego中转站GPT-Image-Grok Image Master.exe"
TARGET = Path(os.environ.get("TEMP", ".")) / "bytego_setup_test"

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
$btnCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Button)
$btns = $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, $btnCond)
$target = $null
foreach ($b in $btns) {
  if ($b.Current.Name -like "*{BTN}*") { $target = $b; break }
}
if (-not $target) { Write-Output "NO_BUTTON"; exit 1 }
Write-Output ("BUTTON='" + $target.Current.Name + "'")
$ip = $null
if ($target.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$ip)) {
  $ip.Invoke()
  Write-Output "INVOKED"
} else {
  Write-Output "NO_INVOKE"
}
'''


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def main() -> int:
    if not SETUP.exists():
        print("未找到安装包：", SETUP)
        return 1
    failures = []

    # ---------------------------------------------------------- 安装
    if TARGET.exists():
        for item in TARGET.glob("*"):
            try:
                item.unlink()
            except OSError:
                pass
    print(f"静默安装到 {TARGET} …")
    proc = run([str(SETUP), "/S", f"/D={TARGET}"], timeout=300)
    time.sleep(6)
    installed_exe = TARGET / EXE_NAME
    print("  安装进程退出码：", proc.returncode)
    if not installed_exe.exists():
        failures.append("安装后主程序缺失")
    if not (TARGET / "uninstall.exe").exists():
        failures.append("安装后卸载器缺失")
    desktop_lnk = Path(os.path.expanduser("~")) / "Desktop" / "Bytego Image Master.lnk"
    if not desktop_lnk.exists():
        failures.append("桌面快捷方式缺失")
    print("  主程序：", installed_exe.exists(), " 卸载器：", (TARGET / 'uninstall.exe').exists(),
          " 桌面快捷方式：", desktop_lnk.exists())

    # ---------------------------------------------------------- 跑一次
    home = Path(os.environ.get("TEMP", ".")) / "bytego_setup_home"
    out_dir = home / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    (home / "history.json").write_text("[]", encoding="utf-8")
    (home / "config.json").write_text(json.dumps({
        "endpoint": "global", "api_key": "sk-demo-local-mock",
        "image_model": "gpt-image-2", "size": "4096x4096",
        "max_retries": 5, "timeout": 1000, "output_dir": str(out_dir),
    }, ensure_ascii=False), encoding="utf-8")

    server = subprocess.Popen([sys.executable, str(ROOT / "tests" / "mock_server.py"), PORT],
                               cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    env = dict(os.environ)
    env["BYTEGO_HOME"] = str(home)
    env["BYTEGO_BASE_URL"] = f"http://127.0.0.1:{PORT}/v1"
    env.pop("QT_QPA_PLATFORM", None)
    app = subprocess.Popen([str(installed_exe)], cwd=str(TARGET), env=env)
    try:
        time.sleep(10)
        out = run(["powershell", "-NoProfile", "-Command",
                   PS_DRIVE.replace("{PROMPT}", "installer e2e prompt")
                            .replace("{BTN}", "生成图片")
                            .replace("{EXE}", str(installed_exe))])
        print("  驱动：", out.stdout.strip().replace("\n", " | "))
        deadline = time.time() + 45
        produced = []
        while time.time() < deadline:
            produced = list(out_dir.glob("*.png"))
            if produced:
                break
            time.sleep(1)
        if not produced:
            failures.append("安装后的程序未能生成图片")
        else:
            data = produced[0].read_bytes()
            ok = len(data) > 1000 and data[:4] == b"\x89PNG"
            print(f"  产出图片：{produced[0].name}（{len(data)} 字节，PNG={ok}）")
            if not ok:
                failures.append("生成的图片无效")
    finally:
        app.terminate()
        server.terminate()
        # PyInstaller onefile 会派生同名子进程，按完整路径清干净再卸载
        for _ in range(30):
            alive = run(["powershell", "-NoProfile", "-Command",
                         f"(Get-Process | Where-Object {{ $_.Path -eq '{installed_exe}' }} | Measure-Object).Count"])
            if alive.stdout.strip() in ("0", ""):
                break
            run(["powershell", "-NoProfile", "-Command",
                 f"Get-Process | Where-Object {{ $_.Path -eq '{installed_exe}' }} | Stop-Process -Force"])
            time.sleep(1)

    # ---------------------------------------------------------- 卸载
    uninstaller = TARGET / "uninstall.exe"
    if uninstaller.exists():
        run([str(uninstaller), "/S"], timeout=180)
        time.sleep(6)
    left = [p.name for p in TARGET.glob("*")] if TARGET.exists() else []
    print("  卸载后残留：", left)
    if left:
        failures.append("卸载后仍有残留：" + ",".join(left))
    if desktop_lnk.exists():
        failures.append("卸载后桌面快捷方式未删除")

    if failures:
        print("\n失败：" + "、".join(failures))
        return 1
    print("\n安装包端到端验证通过：安装 → 出图 → 卸载 全部正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
