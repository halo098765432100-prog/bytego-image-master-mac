"""端到端验证：生成、重试、报错、Agent 工具调用、界面联动。

运行： py -3.13 tests/test_flow.py
"""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("BYTEGO_HOME", str(Path(tempfile.gettempdir()) / "bytego_test_home"))

from tests.mock_server import make_png, serve  # noqa: E402

from bytego_image_master.agent import Agent  # noqa: E402
from bytego_image_master.agent_tools import ToolRunner  # noqa: E402
from bytego_image_master.api import ApiClient, ApiError  # noqa: E402

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = ""):
    (PASS if cond else FAIL).append(name)
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (f" — {detail}" if detail else ""), flush=True)


def wait_for(predicate, timeout=25.0, interval=0.05, tick=None):
    end = time.time() + timeout
    while time.time() < end:
        if tick:
            tick()
        if predicate():
            return True
        time.sleep(interval)
    return False


def main():
    port = 8799
    threading.Thread(target=serve, args=(port,), daemon=True).start()
    time.sleep(0.8)
    base = f"http://127.0.0.1:{port}/v1"
    out_dir = tempfile.mkdtemp(prefix="bytego_test_")

    print("\n== API 客户端 ==")
    client = ApiClient(base, "test-key", timeout=20, max_retries=5)

    retries = []
    res = client.generate_image("retry please", "gpt-image-2", "1024x1024", "auto", 1, "png",
                                output_dir=out_dir,
                                on_retry=lambda a, e: retries.append(a))
    check("重试后成功返回图片", len(res) == 1 and Path(res[0].path).exists(), res[0].path if res else "")
    check("失败重试次数正确(2次)", len(retries) == 2, str(retries))
    check("图片文件非空", Path(res[0].path).stat().st_size > 100 if res else False)

    retries.clear()
    try:
        client.generate_image("always_fail", "gpt-image-2", "1024x1024", "auto", 1, "png",
                              output_dir=out_dir,
                              on_retry=lambda a, e: retries.append(a))
        check("持续失败应抛出异常", False)
    except ApiError as exc:
        check("持续失败应抛出异常", True)
        check("重试满 5 次", len(retries) == 4, f"重试 {len(retries)} 次 + 首次 = 5 次尝试")
        check("报错信息包含上游原文", "mock upstream exploded" in exc.display(), exc.display()[:120])
        check("报错信息含 HTTP 状态码", "HTTP 500" in exc.display())

    try:
        client.generate_image("authfail", "gpt-image-2", "1024x1024", "auto", 1, "png",
                              output_dir=out_dir)
        check("401 应抛异常", False)
    except ApiError as exc:
        check("401 应抛异常", True)
        check("401 报错含中文提示", "API Key" in exc.display(), exc.display()[:120])

    models = client.list_models()
    check("模型列表可用", "gpt-image-2" in models, str(models))

    print("\n== 参考图上传 ==", flush=True)
    from tests.mock_server import STATE

    ref_path = Path(out_dir) / "ref.png"
    ref_path.write_bytes(make_png("REF", (256, 256)))
    before = len(STATE["edits_calls"])
    ref_res = client.generate_image("参考图测试", "gpt-image-2", "1024x1024", "auto", 1, "png",
                                    output_dir=out_dir, reference_images=[str(ref_path)])
    check("带参考图生成成功", len(ref_res) == 1 and Path(ref_res[0].path).exists())
    check("参考图走 images/edits 接口", len(STATE["edits_calls"]) == before + 1,
          str(STATE["edits_calls"][-1:]))
    check("参考图文件已随请求上传",
          bool(STATE["edits_calls"]) and STATE["edits_calls"][-1]["files"] == ["ref.png"],
          str(STATE["edits_calls"][-1] if STATE["edits_calls"] else {}))

    print("\n== Agent 工具调用 ==")
    calls = []

    def fake_confirm(name, args):
        calls.append((name, args))
        return True

    runner = ToolRunner({"allow_command": True}, confirm=fake_confirm)
    agent = Agent(client, runner, model="gpt-4o")
    events = []
    answer = agent.run("tool:cmd", [], on_event=events.append)
    kinds = [e.get("type") for e in events]
    check("触发工具调用事件", "tool_start" in kinds and "tool_end" in kinds, str(kinds))
    check("确认流程被调用", calls and calls[0][0] == "run_command", str(calls))
    tool_result = [e for e in events if e.get("type") == "tool_end"][0]["result"]
    check("命令执行结果正确", "hiliand-agent-ok" in tool_result, tool_result[:120])

    print("\n== 中转站线路与默认值 ==", flush=True)
    from bytego_image_master.config import DEFAULT_CONFIG, ENDPOINTS, endpoint_url

    check("国际站地址恒定", endpoint_url("global") == "https://bytego.team/v1", endpoint_url("global"))
    check("国内直连地址恒定", endpoint_url("cn") == "https://bytego.xyz/v1", endpoint_url("cn"))
    check("默认超时 1000 秒", DEFAULT_CONFIG["timeout"] == 1000, str(DEFAULT_CONFIG["timeout"]))
    check("默认分辨率 4096x4096", DEFAULT_CONFIG["size"] == "4096x4096", DEFAULT_CONFIG["size"])
    check("默认线路为国际站", DEFAULT_CONFIG["endpoint"] == "global", DEFAULT_CONFIG["endpoint"])
    check("只有两条固定线路", len(ENDPOINTS) == 2, str(list(ENDPOINTS)))

    print("\n== 界面联动 ==", flush=True)
    from PyQt5.QtWidgets import QApplication, QScrollArea, QWidget
    from bytego_image_master.ui.main_window import MainWindow

    # base url 恒定为中转站地址，只有测试通过环境变量指向本地 mock
    os.environ["BYTEGO_BASE_URL"] = base

    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.show()
    app.processEvents()
    win.history = []
    win.apply_settings({"api_key": "test-key", "output_dir": out_dir,
                        "max_retries": 5, "timeout": 20})
    win.page_generate.prompt.setPlainText("界面联动测试")
    win.page_generate.start_generate()
    ok = wait_for(lambda: bool(win.history) and win.page_generate.task is not None
                  and not win.page_generate.task.isRunning(), 25, tick=app.processEvents)
    app.processEvents()
    check("界面生成成功并写入历史", ok and len(win.history) == 1, str(win.history[:1]))
    check("历史记录含提示词与路径",
          bool(win.history) and "界面联动测试" in win.history[0]["prompt"]
          and Path(win.history[0]["path"]).exists())

    # --- 界面上的参考图上传
    added = win.page_generate.ref_strip.add_files([str(ref_path)])
    check("参考图可加入队列", added == 1 and win.page_generate.ref_strip.count() == 1)
    check("加入后提示已更新", "1 张参考图" in win.page_generate.ref_hint.full_text(),
          win.page_generate.ref_hint.full_text())
    before_edits = len(STATE["edits_calls"])
    win.page_generate.prompt.setPlainText("带参考图的界面测试")
    win.page_generate.start_generate()
    ok_ref = wait_for(lambda: win.page_generate.task is not None
                       and not win.page_generate.task.isRunning(), 25, tick=app.processEvents)
    app.processEvents()
    check("带参考图生成成功", ok_ref and len(win.history) == 2
          and win.history[0]["prompt"] == "带参考图的界面测试", str(win.history[:1]))
    check("界面参考图走了 edits 接口", len(STATE["edits_calls"]) == before_edits + 1,
          str(STATE["edits_calls"][-1:]))
    win.page_generate.ref_strip.clear()
    check("参考图可清空", win.page_generate.ref_strip.count() == 0)

    win.switch_page(1)
    app.processEvents()
    check("作品库切页正常", win.stack.currentIndex() == 1)
    win.switch_page(2)
    app.processEvents()
    check("Agent 页切页正常", win.stack.currentIndex() == 2)
    win.switch_page(3)
    app.processEvents()
    check("设置页切页正常", win.stack.currentIndex() == 3)
    check("设置页不再提供自由 base url 输入框",
          not hasattr(win.page_settings, "base_url"))
    check("设置页提供两条固定线路单选",
          len(getattr(win.page_settings, "endpoint_buttons", {})) == 2)
    win.apply_settings({"base_url": "https://not-allowed.example/v1"})
    check("外部无法改写 base url", win.cfg.get("base_url") == base, str(win.cfg.get("base_url")))

    os.environ.pop("BYTEGO_BASE_URL", None)
    win.apply_settings({"endpoint": "cn"})
    check("切换国内直连后地址跟随线路", win.cfg.get("base_url") == "https://bytego.xyz/v1",
          str(win.cfg.get("base_url")))
    win.apply_settings({"endpoint": "global"})
    check("切回国际站地址", win.cfg.get("base_url") == "https://bytego.team/v1",
          str(win.cfg.get("base_url")))
    os.environ["BYTEGO_BASE_URL"] = base
    win.cfg["base_url"] = base
    win.client = win._build_client()

    print("\n== 布局与模型选择 ==", flush=True)
    win.switch_page(0)
    for size in ((1180, 760), (1100, 700), (1600, 900)):
        win.resize(*size)
        app.processEvents()
        scroll = win.page_generate.findChildren(QScrollArea)[0]
        host = scroll.widget()
        need = host.minimumSizeHint().width()
        have = scroll.viewport().width()
        check(f"窗口 {size[0]}x{size[1]} 左侧内容不被裁切", need <= have,
              f"需要 {need}px / 视口 {have}px")
    check("提示词框会换行", win.page_generate.prompt.lineWrapMode()
          == win.page_generate.prompt.WidgetWidth)

    win.set_models(["gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst", "gpt-4o"])
    app.processEvents()
    picker = win.page_generate.picker
    check("模型复选框列表已填充", len(picker._models) == 4, str(picker._models))
    picker._on_toggled("gpt-image-2.5-sunburst", True)
    picker._on_toggled("gpt-image-2", True)
    app.processEvents()
    check("勾选顺序即优先级", win.model_selection() == ["gpt-image-2.5-sunburst", "gpt-image-2"],
          str(win.model_selection()))
    check("默认模型跟随首个勾选", win.cfg.get("image_model") == "gpt-image-2.5-sunburst",
          str(win.cfg.get("image_model")))
    check("生成页与设置页共用同一份选择",
          win.page_settings.image_model.selected_models() == win.model_selection(),
          str(win.page_settings.image_model.selected_models()))
    win.page_generate.picker.search.setText("flare")
    app.processEvents()
    check("模型筛选可用", len(picker._models) == 4)
    win.page_generate.picker.search.setText("")

    print("\n== 取消与模型回退 ==", flush=True)
    errors = []
    win.show_error = lambda title, message: errors.append((title, message))
    win.page_generate.picker.set_selection(["gpt-image-2"])
    win.page_generate.prompt.setPlainText("slow 取消测试")
    win.page_generate.start_generate()
    wait_for(lambda: win.page_generate.task is not None
             and win.page_generate.task.isRunning(), 5, tick=app.processEvents)
    check("生成中按钮置灰", not win.page_generate.gen_btn.isEnabled())
    check("生成中显示进度条", win.page_generate.progress.isVisible())
    win.page_generate.cancel_generate()
    done = wait_for(lambda: win.page_generate.task is not None
                    and not win.page_generate.task.isRunning(), 15, tick=app.processEvents)
    app.processEvents()
    check("取消后任务结束", done)
    check("取消后按钮恢复", win.page_generate.gen_btn.isEnabled()
          and win.page_generate.gen_btn.text() == "生成图片")
    check("取消后状态提示已取消", "取消" in win.page_generate.status.text(),
          win.page_generate.status.text())

    win.page_generate.picker.set_selection(["gpt-image-2", "gpt-image-1"])
    win.page_generate.prompt.setPlainText("always_fail 触发回退")
    win.history = []
    win.apply_settings({"max_retries": 1})
    win.page_generate.start_generate()
    ok2 = wait_for(lambda: win.page_generate.task is not None
                   and not win.page_generate.task.isRunning(), 40, tick=app.processEvents)
    app.processEvents()
    check("全部模型失败后报错", ok2 and not win.history)
    check("失败后按钮恢复", win.page_generate.gen_btn.isEnabled())
    check("错误弹窗收到完整信息", bool(errors) and "mock upstream exploded" in errors[-1][1],
          str(errors[-1])[:160] if errors else "无")

    from bytego_image_master.config import load_config, save_config
    saved = dict(win.cfg)
    saved["api_key"] = "sk-persist-check"
    saved["max_retries"] = 5
    saved["timeout"] = 180
    saved["output_dir"] = out_dir
    win.apply_settings(saved)
    win2 = MainWindow()
    check("启动不会覆盖已保存配置", win2.cfg.get("api_key") == "sk-persist-check"
          and win2.cfg.get("max_retries") == 5 and win2.cfg.get("timeout") == 180,
          f"key={win2.cfg.get('api_key')!r} retries={win2.cfg.get('max_retries')} "
          f"timeout={win2.cfg.get('timeout')}")

    print("\n== Mac 移植分支 ==")
    import tempfile as _tf
    from unittest import mock

    from bytego_image_master import platforms
    from bytego_image_master.agent_tools import ToolRunner as _TR
    from bytego_image_master.config import data_dir as _data_dir
    from bytego_image_master.ui.main_window import enable_dark_titlebar

    fake_home = Path(_tf.mkdtemp(prefix="bytego_mac_home_"))
    with mock.patch.dict(os.environ), mock.patch("sys.platform", "darwin"), \
            mock.patch.object(Path, "home", return_value=fake_home):
        os.environ.pop("BYTEGO_HOME", None)
        os.environ.pop("HILIAND_HOME", None)
        check("mac 配置目录指向 Application Support",
              str(_data_dir()) == str(fake_home / "Library" / "Application Support" / "BytegoImageMaster"),
              str(_data_dir()))
        argv_mac = platforms.shell_argv("echo hi", "powershell")
        check("mac run_command 固定 zsh", argv_mac == ["/bin/zsh", "-lc", "echo hi"], str(argv_mac))
        opened = []
        with mock.patch.object(platforms.subprocess, "Popen", lambda a, **k: opened.append(a)):
            platforms.open_in_file_manager(fake_home)
            check("mac 打开目录走 open 命令", bool(opened) and opened[0][0] == "open", str(opened))
        check("mac Agent 提示词 shell 名称", platforms.shell_tool_label() == "zsh",
              platforms.shell_tool_label())
        cap = {}

        def fake_run(argv, **kwargs):
            cap["argv"] = argv

            class P:
                returncode, stdout, stderr = 0, "ok", ""
            return P()

        with mock.patch("bytego_image_master.agent_tools.subprocess.run", fake_run):
            runner_mac = _TR({"allow_command": True}, confirm=lambda *a, **k: True)
            out_mac = runner_mac._run_command({"command": "echo hi"})
        check("mac ToolRunner 实际调用 /bin/zsh", cap.get("argv", [""])[0] == "/bin/zsh",
              str(cap.get("argv")))
        check("mac run_command 返回结果", "退出码：0" in out_mac and "ok" in out_mac, out_mac[:60])
        enable_dark_titlebar(win)  # mac 分支应直接返回，不触碰 ctypes.windll
        check("mac 深色标题栏分支安全返回", True)

    check("Windows run_command cmd 分支保留", platforms.shell_argv("dir", "cmd") == ["cmd.exe", "/c", "dir"])
    check("Windows Agent 提示词 shell 名称", platforms.shell_tool_label() == "PowerShell",
          platforms.shell_tool_label())

    print(f"\n结果：通过 {len(PASS)}，失败 {len(FAIL)}")
    if FAIL:
        print("失败项：" + "、".join(FAIL))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
