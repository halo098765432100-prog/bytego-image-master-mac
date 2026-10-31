# Bytego中转站GPT-Image/Grok Image Master

一款用 PyQt5 写的桌面图片生成工具：通过 **Bytego 中转站**调用 GPT-Image / Grok Image 系列模型出图，同时内置一个由 GPT 模型驱动的**本地 Agent**，可以帮你在本机上执行命令、读写文件、调用出图。

- 接口地址**恒定**为 Bytego 两个端点之一，界面上没有 Base URL 输入框，不会填错
- **API Key 自己在设置页粘贴**，只保存在本机 `config.json`
- **支持上传参考图**（图生图）：按钮选图或直接把图片拖进界面，最多 6 张
- 生成路径全异步（QThread），出图不卡界面
- 接口出错自动重试 **5 次**，并把完整报错弹窗 + 记入底部日志
- 四个页面：生成图片 / 作品库 / 本地 Agent / 设置
- 深色自绘主题（QSS），已打包为**安装包（setup）**，双击安装即用，无需装 Python
- **复选框模型选择器**：拉到的模型可任意勾选多个，按勾选顺序依次兜底尝试
- **生成过程有强烈反馈**：阶段指示器、动态光晕占位、平滑进度条、大号秒表、出图闪光，随时可**取消**
- 左右分栏可拖拽，窗口任意缩放都不会把提示词或参数裁掉

---

## 一、安装

安装包（Windows 10/11，64 位）：

```
dist\Bytego中转站GPT-Image-Grok Image Master-Setup-1.1.0.exe
```

双击后会依次出现：欢迎页 → 使用许可 → 安装目录 → 安装进度 → 完成页（可勾选「立即启动」）。

安装程序会：

- 把主程序装到 `%LOCALAPPDATA%\Programs\BytegoImageMaster`（默认目录，可在安装页改）
- 在桌面和开始菜单创建快捷方式
- 在「设置 → 应用 → 已安装的应用」里登记卸载项（`uninstall.exe`，可静默卸载：`uninstall.exe /S`）

> 单文件免安装版也在 `dist\` 里：`Bytego中转站GPT-Image-Grok Image Master.exe`，双击即用，不写注册表、不建快捷方式。

程序首次启动时会自动创建配置目录：

```
%APPDATA%\BytegoImageMaster\
├── config.json     线路、Key、模型、默认参数、Agent 权限
└── history.json    生成记录（最多保留 500 条）
```

想把它当成"绿色便携版"，只要在启动前设置环境变量 `BYTEGO_HOME` 指向自选目录，配置和历史就会落在那里。

---

## 二、第一次使用：三步配置

打开左下角 **设置** 页面：

| 字段 | 说明 |
| --- | --- |
| **中转站线路** | 单选，只有两条且**地址固定**：国际站 `https://bytego.team/v1`（默认）、国内直连 `https://bytego.xyz/v1`。切换后立即生效，界面里无法手写别的地址 |
| **API Key** | 在 Bytego 控制台申请后粘贴到这里，只保存在本机 `config.json`，不会外发到 Bytego 以外的任何地方（输入框默认打码，点「显示」可查看） |
| **超时（秒）** | 单次请求超时上限，默认 **1000** 秒（高分辨率出图很慢，1000 秒足够跑满一张大图） |

填完点 **测试连接**：能拉到模型列表说明线路和 Key 正确，**生成页和设置页的模型列表会同时刷新**。

---

## 三、生成图片

左侧 **生成图片** 页面（左右分栏，中间分隔条可拖拽；左栏上半部分可滚动，**生成按钮固定在左栏底部**，滚动时也一直点得到，提示词和参数不会被裁切）：

- **提示词**：直接写，或点右上角 **风格标签** 菜单（电影感光影 / 写实摄影 / 插画风格 / 赛博朋克 / 水彩画 / 3D 渲染 / 动漫二次元 / 极简海报）快速追加描述；下方实时显示字数
- **图像模型**：点 **拉取模型列表** 从服务端拉取可用模型，列表以**复选框**呈现，可同时勾选多个
  - 勾选顺序 = 优先级，勾上的模型左边会显示蓝色角标 `1` `2` `3`，`1` 是主用模型，后面依次是备用
  - 第一个失败会自动换下一个继续试（见第四节）
  - 复选框上方可输入关键字过滤模型名
  - 右上角显示「已选 N / 共 M 个」，下方提示「当前使用：X（备用 N 个）」
  - 生成页与设置页共用同一份选择，两边改一边另一边同步
- **尺寸**：默认 **4096x4096**，另有 `2048x2048`、`1536x1024`、`1024x1536`、`1024x1024`、`1792x1024`、`1024x1792`，也可手填自定义值（边长为 16 的倍数、长宽比不超过 3:1）
- **质量**：自动 / 快速 / 标准 / 精细 / 超精细 / 最高（对应 `auto` / `low` / `medium` / `high` / `xhigh` / `max`）
- **数量**：一次出 1~4 张
- **格式**：`png` / `jpeg` / `webp`
- **透明背景**：勾选后背景为透明
- **参考图**（可选）：点「上传参考图」多选图片，或把图片**直接拖进虚线区域**，最多 6 张；每张可单独「移除」
  - 带参考图时请求走 `POST /v1/images/edits`（multipart 上传），单张用 `image` 字段，多张用 `image[]`
  - 如果当前线路没有这个接口，程序会自动退回纯文生图，并在状态栏提示「当前线路不支持参考图上传，已改为纯文本生成」，不会静默丢掉你的图

点 **生成图片**（或按 `Ctrl+Enter`）开始。右侧实时显示预览和缩略图，可 **放大** / **打开目录**。

图片自动保存到「设置 → 输出目录」（默认 `Pictures\BytegoImageMaster`），文件名形如 `bytego_20261031_165249_9866.png`，同时写入作品库。

### 快捷键

| 按键 | 作用 |
| --- | --- |
| `Ctrl+Enter` | 开始生成 |
| `Ctrl+L` | 定位到提示词输入框 |
| `Ctrl+1` ~ `Ctrl+4` | 切换到 生成 / 作品库 / Agent / 设置 页 |

### 生成过程中

点击生成后，界面会立刻进入"忙碌"状态，不会让人干等：

- **阶段指示器**：准备 → 连接 → 绘制 → 保存 → 完成，当前阶段高亮并带呼吸光晕，已完成的阶段变成绿色
- **预览区动态光晕**：斜向扫光 + 中心光晕 + 旋转弧 + 呼吸外圈，主文案显示「<模型> 正在生成 4096x4096」，下面的小文案循环滚动（正在理解你的提示词… / 正在构图与配色… / 正在渲染光影细节… / 正在输出高分辨率成图…）
- **平滑进度条**：向阶段目标缓动，绘制阶段还会持续缓慢上爬，等待过程始终"有反应"
- **大号秒表**：底部右侧实时显示已用秒数（`12.4s`），状态行同步显示「正在连接 bytego.team … · 12.4s」
- **生成图片** 按钮变为「生成中…」并禁用，**取消** 按钮变为可用
- 再次点 **取消** 会真正中断 HTTP 请求（关闭连接），不用等到超时
- 出图瞬间预览区闪一下白光，右下角弹出成功提示（Toast）；失败则弹出完整错误信息
- 作品库每张图下面有 **用这条提示词再生成**，点一下就带着原提示词跳回生成页

---

## 四、重试与报错

失败不是静默的：

1. **自动重试 5 次**。5 次是**总尝试次数**（第 1 次请求 + 最多 4 次重试），每次失败后按 1.2s → 2.4s → 3.6s … 递增等待，单次最多等 6 秒。
2. **过程中有反馈**：状态栏实时显示"第 N/M 次失败：<原因> — 正在重试…"，M 就是设置里的重试次数。
3. **全部失败才弹窗**，弹窗内容包含三部分：
   - HTTP 状态码（没有状态码时显示网络层原因）
   - 服务端返回的原始报错信息
   - 一句中文处置建议（401 → Key 无效；404 → 检查线路是否含 `/v1`；429 → 频率或额度；502/503 → 服务暂时不可用…）
4. **底部日志留档**：底部状态栏显示最近一条日志，点右侧 **查看日志** 可看全部（最多 800 行）。生成成功、参数变更、线路切换、连接测试、每次重试都会写进日志。

失败不会丢参数：提示词和参数原样保留，改完直接再点一次即可。

### 多模型兜底

勾选了多个模型时，每个模型各自走完整的 5 次重试；某个模型彻底失败会自动切到下一个模型继续（状态栏会提示"切换到下一个模型"）。
所有模型都失败后，弹窗标题为「生成失败」，内容形如：

```
已依次尝试 2 个模型（gpt-image-2、gpt-image-1）仍失败：
HTTP 500 · mock upstream exploded
```

---

## 五、本地 Agent

左侧 **本地 Agent** 页面，用 GPT 模型（默认 `gpt-4o`，可切换）驱动本机操作。

内置工具：

| 工具 | 作用 | 默认权限 |
| --- | --- | --- |
| `run_command` | 执行 PowerShell 命令（超时上限 300 秒，返回 stdout / stderr / 退出码） | 需确认 |
| `read_file` | 读取文本文件 | 需确认 |
| `write_file` | 写入文本文件 | 需确认 |
| `list_directory` | 列目录 | 需确认 |
| `open_path` | 用系统默认程序打开文件或目录 | 需确认 |
| `generate_image` | 调用同一个出图接口生成图片 | 需确认 |
| `list_history` | 读取历史生成记录 | 需确认 |

右侧面板可以逐项开关权限（**允许执行命令行 / 允许写入文件 / 允许打开路径 / 允许 Agent 触发生成**），也可以打开 **危险操作免确认** 跳过弹窗。默认全部关闭免确认：每个高风险工具执行前都会弹确认框，写明具体要执行什么。

对话是流式的，模型输出逐字显示；工具调用会单独渲染成一张卡片（工具名 + 参数 + 返回结果）。

> Agent 能做的事完全取决于你在设置里给的权限和模型返回的工具调用。命令在当前用户身份下执行，没有额外提权。

---

## 六、开发者

| | |
| --- | --- |
| 开发者 | **NL-1234** |
| QQ | **2265242381** |

侧栏底部有独立的 **「开发者信息」** 按钮，点开是弹窗：软件名与版本、开发者、QQ（带「复制」按钮）、当前中转站线路与地址。设置页最下方也有同一个入口。

---

## 七、常见问题

**测试连接失败 / 404**
Bytego 两个端点都已自带 `/v1`，切换线路后不需要再补路径；如果仍 404，多半是 Key 不属于当前线路。

**401**
API Key 没填或填错；确认它接受 `Authorization: Bearer <key>` 头。

**国内访问慢 / 不稳**
在设置页把线路切到 **国内直连**（`https://bytego.xyz/v1`），地址会自动跟着切换。

**出图很慢**
图片模型没有流式返回，只能等整图生成完。默认超时已经是 1000 秒；急用可以在设置里调小超时，或改用更快的质量档（快速 / 标准）。

**想要透明背景**
格式选 `png` 并勾选「透明背景」；`jpeg` 不支持透明。

**换电脑 / 换目录**
把 `%APPDATA%\BytegoImageMaster\config.json` 拷过去即可（含 Key 和全部设置）。

---

## 八、从源码运行与重新打包

环境：Python 3.13

```bash
pip install pyqt5 requests pillow pyinstaller

# 直接运行
py -3.13 main.py

# 跑离线测试（自带 mock 服务，不需要真实 API）
py -3.13 tests/test_flow.py

# 重新生成图标（PNG + ICO）
py -3.13 make_icon.py

# 打包成单文件 exe
py -3.13 build.py

# 打包成 Windows 安装包（需要 NSIS 3.x）
py -3.13 build_installer.py
```

`build.py` 会先清空 `build/` 和 `dist/`，再调 PyInstaller 重新打包，产物是 `dist\Bytego中转站GPT-Image-Grok Image Master.exe`（约 46 MB，已包含 PyQt5、requests、Pillow 与图标资源）。

`build_installer.py` 调用 NSIS（`makensis`）把单文件 exe 与图标打进 `dist\Bytego中转站GPT-Image-Grok Image Master-Setup-1.1.0.exe`（约 47 MB），安装向导逻辑写在 `installer.nsi`。

### macOS 打包（.dmg）

代码已做 Mac 移植（配置目录 `~/Library/Application Support/BytegoImageMaster`、访达打开、Agent 用 zsh），Windows 行为不受影响。打包必须在 Mac 上执行（PyInstaller 不支持跨平台），在项目根目录跑一条命令：

```bash
bash mac/build_mac.sh
```

脚本会自动建虚拟环境、装依赖、用 `mac/BytegoImageMaster_mac.spec` 产出 `dist/Bytego Image Master.app`、做 ad-hoc 签名，再用 `hdiutil` 压成 `dist/Bytego中转站GPT-Image-Grok Image Master-<版本>.dmg`（.app 与 Applications 软链并排，拖拽安装）。`resources/icon.icns` 由 `py -3.13 mac/gen_icns.py` 生成（Windows 上即可生成，已提交）。

未签名 App 首次打开：右键 →「打开」，或 系统设置 → 隐私与安全性 →「仍要打开」；也可终端执行 `xattr -cr "/Applications/Bytego Image Master.app"`。要对外正式分发需 Apple Developer ID 签名 + 公证。

> Apple Silicon 排障：若 PyQt5 装不上（无 arm64 轮子），换 Rosetta 版 Python 再跑：`PY=arch -x86_64 python3 bash mac/build_mac.sh` 不行的话直接 `arch -x86_64 /usr/local/bin/python3 -m venv .venv-mac` 后重跑脚本。

项目结构：

```
main.py                        入口
build.py                       打包脚本（单文件 exe）
build_installer.py             打包脚本（NSIS 安装包）
installer.nsi                  安装向导脚本
license.txt                    安装包里的使用许可
requirements.txt               Python 依赖（Windows/macOS 通用）
make_icon.py                   图标生成
mac/                           macOS 打包（spec / build_mac.sh / gen_icns.py）
version_info.txt               exe 版本信息
bytego_image_master/
├── config.py                  固定线路、配置与历史读写（配置目录分平台）
├── platforms.py               平台差异（打开目录、Agent shell）
├── api.py                     接口封装、重试、错误信息、参考图上传
├── agent.py                   Agent 主循环（function calling）
├── agent_tools.py             本地工具定义与权限
├── theme.py                   配色与 QSS
├── resources/                 图标
└── ui/
    ├── main_window.py         主窗口与页面调度
    ├── pages_generate.py      生成图片
    ├── pages_gallery.py       作品库
    ├── pages_agent.py         本地 Agent
    ├── pages_settings.py      设置
    ├── widgets.py             通用组件（阶段指示器、动态画布、参考图区、开发者弹窗）
    └── workers.py             后台线程
tests/
├── mock_server.py             本地 mock OpenAI 服务（含 images/edits）
├── test_flow.py               端到端测试
├── verify_exe.py              打包产物端到端验证
├── screenshot.py              自动截图
├── shot_dialog.py             离屏渲染弹窗
└── shot_dialog_win.py         真窗口截图弹窗
```
