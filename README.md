# EE6008 驾驶员面部疲劳感知系统

这是一个本地优先、平台中立的驾驶员状态监测项目。当前第一版使用摄像头或视频文件找到面部关键点，通过 EAR、MAR、PERCLOS 和真实时间状态机判断持续闭眼、打哈欠与疲劳风险。

第一版不识别驾驶员身份，不会自动上传人脸画面，也不依赖 NVIDIA 显卡。

## 当前已经具备

- MediaPipe 单人脸 478 个关键点检测；
- 启动时约 5 秒个人阈值校准；
- EAR 眼睛开合、持续闭眼与 PERCLOS；
- MAR 持续张嘴和时间窗口内哈欠计数；
- `NORMAL / WARNING / DANGER` 三级状态及可解释原因；
- 摄像头和本地视频两种输入；
- OpenCV 实时画面与 JSONL 状态变化日志；
- 本地 Web 前端仪表盘，包括实时画面、状态卡、指标卡和事件列表；
- YOLO26n 手机检测、置信度、画面标框和持续出现提醒；
- 与帧率无关的时间判断；
- 纯逻辑自动化测试。

目前已经在 Apple M2 Mac 上完成视频和摄像头的 CPU 验证。跨平台代码、启动脚本和三系统自动测试配置已经加入，但 Windows、Linux 和 NVIDIA GPU 仍需要在对应电脑上实测后才能确认。

## 文件位置

- `src/driver_monitor/`：程序代码；
- `configs/default.yaml`：摄像头、校准和疲劳阈值；
- `tests/`：自动化测试；
- `scripts/download_face_model.py`：下载并校验官方面部模型；
- `scripts/download_phone_model.py`：下载并校验官方YOLO26n权重；
- `driver-monitor-doctor`：不打开摄像头的环境诊断命令；
- `.github/workflows/cross-platform-tests.yml`：Windows、macOS、Linux 单元测试配置；
- `docs/从零开始_完整开发流程.md`：零基础学习和开发路线；
- `课程官方资料/`、`项目汇报/`、`参考研究/`、`课堂记录/`：原始课程资料，开发时不修改。

`.venv/`、`models/`、`outputs/` 都是本地运行内容，不上传 GitHub。

## 不方便测试摄像头时

可以先运行只读环境检查，它不会打开摄像头：

```bash
driver-monitor-doctor
```

把诊断结果交给 AI 时，使用结构化输出：

```bash
driver-monitor-doctor --json
```

只有明确加上 `--camera` 才会尝试打开并立即释放摄像头。手机检测设备默认设为 `auto`：优先 NVIDIA CUDA，其次 Apple MPS，两者都不可用时使用 CPU。也可以在 `configs/default.yaml` 中明确写成 `cpu`、`mps`、`cuda` 或 `cuda:0`；指定的加速设备不可用时会安全回退到 CPU，并在诊断结果中说明原因。

## Mac 第一次运行

在本文件所在文件夹打开终端，然后依次执行：

```bash
/opt/homebrew/bin/python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[actions]'
python scripts/download_face_model.py
python scripts/download_phone_model.py
python -m unittest discover -s tests -v
driver-monitor-web
```

首次打开摄像头时，按照 macOS 提示允许访问。若之前拒绝过，请打开：

```text
系统设置 → 隐私与安全性 → 摄像头 → 允许 Codex 或 Terminal
```

重新启动 Codex/Terminal 后再运行 `driver-monitor`。

也可以在 Finder 中双击 `启动疲劳监测.command`，程序会启动本地 Python 服务并自动用浏览器打开 `http://127.0.0.1:8000`。启动后点击“开始监测”，先正常睁眼、闭嘴看镜头约 5 秒。校准结束后，网页会显示状态、EAR、MAR、PERCLOS、近期哈欠次数和报警原因。

仪表盘支持：

- 开始和停止摄像头；
- 手动重新校准；
- 在摄像头与本地视频之间切换；
- 绿色、橙色、红色状态提示；
- 查看状态变化事件。

检测算法、摄像头和日志仍由 Python 负责；HTML、CSS 和 JavaScript 只负责浅色仪表盘展示。网页地址只绑定本机，不会把摄像头画面发布到网络。

仪表盘提供 English / 中文切换，第一次打开默认使用英文，并记住上次选择。教授演示时可直接打开 `http://127.0.0.1:8000/?lang=en`，强制进入英文界面。按钮、校准提示、指标、手机状态和事件记录均随语言切换，监测数据和阈值不变。英文口头说明见 [教授口头汇报_启动校准与手机检测.md](docs/教授口头汇报_启动校准与手机检测.md)。

仪表盘现在也显示 MediaPipe 给出的头部俯仰、左右转动和侧倾角度。经过真人动作校准后，持续低头或偏离前方超过2秒会触发提醒；姿态明显偏离时，系统会暂停使用容易失真的EAR/MAR数据，避免把低头误判为闭眼或把大角度转头误判为哈欠。

手机检测使用COCO预训练的轻量YOLO26n，只请求“cell phone”类别。手机连续出现2秒后提醒，画面上显示检测框和置信度。当前只能证明“画面中出现手机”，不能仅凭这一项严格证明驾驶员正在使用手机；需要结合位置、头部姿态和更多真人场景继续减少误报。

如果需要备用的 Python 桌面界面，可以运行：

```bash
driver-monitor-gui
```

如果只需要最简调试窗口，可以运行：

```bash
driver-monitor
```

最简调试窗口按 `Q` 或 `Esc` 退出。

## Windows 和 Linux 准备入口

Windows 原生 PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
```

安装完成后双击 `检查运行环境.bat`，确认无误再双击 `启动疲劳监测.bat`。

Ubuntu/Linux：

```bash
./scripts/setup_unix.sh
./检查运行环境.sh
./启动疲劳监测.sh
```

这两套脚本已经写入仓库，但目前还没有在 Windows/Linux 实机运行。摄像头最容易先在 Windows 原生环境测试；WSL2 对 USB 摄像头的转接更复杂，不作为第一轮验收路径。完整迁移步骤和验收边界见 [Windows迁移与AI运行指南.md](Windows迁移与AI运行指南.md)。

## 分析本地视频

```bash
driver-monitor --video /完整路径/测试视频.mp4
```

不显示窗口、只生成事件日志：

```bash
driver-monitor --video /完整路径/测试视频.mp4 --headless
```

状态变化写入 `outputs/events.jsonl`，默认不保存原始视频。

## 必须知道的限制

- 第一次校准时必须正常睁眼、闭嘴；否则个人阈值会不准确。
- 暗光、遮挡、强侧脸、墨镜和摄像头位置会影响关键点。
- 哈欠只能由“持续张嘴”近似判断，说话可能造成误报，需要真人实验后调整。
- 手机太小、被手遮挡或移出画面时可能漏检；桌面手机若清晰入镜也可能被当成正在使用。
- Ultralytics代码与模型采用AGPL-3.0开源许可，本课程开源研究原型可以使用；闭源商业用途需要重新评估许可。
- 当前是课程研究原型，不是汽车安全产品或医疗设备。
- 自动设备选择不等于 GPU 已验证；必须在 NVIDIA 电脑上看到诊断为 `cuda:0` 并完成真实推理，才能宣称 GPU 可用。
- 不要在真实驾驶过程中闭眼做测试，只能在静止、安全环境模拟。

手机基线依据[Ultralytics官方YOLO26文档](https://docs.ultralytics.com/models/yolo26)与[官方许可说明](https://docs.ultralytics.com/#yolo-licenses-how-is-ultralytics-yolo-licensed)。后续继续增加视线/手部关系、跨平台验证和可选云端分析。详细原理与验收方法见 [从零开始_完整开发流程.md](docs/从零开始_完整开发流程.md)。
