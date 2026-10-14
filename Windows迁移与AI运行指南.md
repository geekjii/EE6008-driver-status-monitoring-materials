# Windows、Linux 与 NVIDIA 迁移指南

这份文件给第一次迁移项目的组员，也给接手运行项目的 AI。它把“代码已经准备好”和“对应平台已经实测”分开记录，避免误把脚本存在当成迁移完成。

## 1. 当前状态

| 项目 | 当前状态 | 证据或下一步 |
|---|---|---|
| Apple M2 Mac、CPU | 已实测 | 本地视频、摄像头和网页流程已有运行记录 |
| 自动选择 CPU/MPS/CUDA | 代码及单元测试完成 | 当前 Mac 实际选择 CPU；模拟后端测试覆盖 CUDA、MPS 和回退 |
| 无摄像头环境诊断 | 已在当前 Mac 实测 | `driver-monitor-doctor` 检查依赖、模型、配置、设备和日志目录 |
| Windows 原生启动 | 脚本已准备，未实机验证 | 在 Windows 11 电脑运行 `scripts\setup_windows.ps1` |
| Ubuntu/Linux 启动 | 脚本已准备，未实机验证 | 在 Linux 电脑运行 `scripts/setup_unix.sh` |
| 三系统自动测试 | 工作流已配置，未取得云端结果 | 推送到 GitHub 后查看 Actions |
| NVIDIA CUDA 推理 | 未实机验证 | 需要 RTX 电脑、驱动检查和真实视频推理 |
| Docker/TensorRT | 尚未开始 | CPU 和 CUDA 原生流程稳定后再做 |

## 2. 固定的软件基线

- Python：3.11.x
- PyTorch：2.13.0
- torchvision：0.28.0
- Ultralytics：8.4.135
- OpenCV contrib：4.11.0.86
- 其余 Python 版本记录在 `pyproject.toml`

CUDA 版本暂时没有写死，因为尚未在目标 NVIDIA 电脑上核对驱动和 PyTorch 运行时。不要为了看起来完整而猜一个 CUDA 版本。先完成第 5 节的诊断，再基于目标电脑结果固定。

## 3. Windows 原生安装（第一推荐路径）

先安装 64 位 Python 3.11，并确保 Python Launcher `py` 可用。然后在项目根目录打开 PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
```

脚本会创建项目自己的 `.venv`、安装固定依赖、下载并校验两份模型、运行单元测试和无摄像头诊断。它不会主动打开摄像头。

安装结束后可以双击：

- `检查运行环境.bat`：只检查环境；
- `启动疲劳监测.bat`：启动本地网页。

网页地址为 `http://127.0.0.1:8000`。首次点击“开始监测”时，Windows 可能要求摄像头权限。只能在静止、安全环境中模拟动作。

## 4. Ubuntu/Linux 安装

安装 Python 3.11 和创建虚拟环境所需的系统包后，在项目根目录运行：

```bash
./scripts/setup_unix.sh
./检查运行环境.sh
./启动疲劳监测.sh
```

如果系统中的 Python 3.11 命令不是 `python3.11`，可以这样指定：

```bash
PYTHON_COMMAND=/完整路径/python3.11 ./scripts/setup_unix.sh
```

WSL2 可以用于代码和 GPU 开发，但第一轮摄像头验收建议使用 Windows 原生环境。WSL2 中转接 USB 摄像头需要额外配置，会把“算法是否工作”和“设备是否成功转接”两个问题混在一起。

## 5. NVIDIA 电脑验收

先运行：

```powershell
nvidia-smi
.venv\Scripts\driver-monitor-doctor.exe --json
```

诊断结果中的 `inference_device.resolved` 应为 `cuda:0`。如果仍为 `cpu`，先不要运行摄像头，也不要声称 GPU 已经可用；应检查 NVIDIA 驱动、PyTorch 安装来源和 `torch.cuda.is_available()`。

诊断通过后依次验证：

1. 用同一段本地视频跑 CPU；
2. 把 `configs/default.yaml` 中的 `phone.device` 改为 `cuda:0`，跑同一视频；
3. 对比状态日志、处理 FPS、手机检测结果和错误信息；
4. 最后才打开摄像头测试。

Ultralytics 的推理接口接受 `cpu`、CUDA 设备编号等设备设置；Apple Silicon 也支持 `mps`。本项目在这些设置前增加了可用性检查和 CPU 回退。参考 [Ultralytics Predict 官方文档](https://docs.ultralytics.com/modes/predict/) 和 [Ultralytics Train 官方文档](https://docs.ultralytics.com/modes/train/)。

## 6. 自动测试

`.github/workflows/cross-platform-tests.yml` 会在 GitHub 托管的 `ubuntu-latest`、`macos-latest` 和 `windows-latest` 环境安装 CPU 基线、编译源码并运行单元测试。工作流文件存在不代表三系统已经通过；必须在 GitHub Actions 页面看到三项绿色结果，才可以记录为 CI 通过。运行环境标签依据 [GitHub 托管运行器文档](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job)。

## 7. 迁移时必须保留的规则

- 使用 `pathlib` 和项目相对路径，不写死某台电脑的用户目录；
- `.venv/`、`models/`、`outputs/`、私人视频和数据集不上传；
- 状态判断使用真实时间或视频时间戳，不使用固定帧数冒充秒数；
- CPU 始终是最低可运行路径；
- Windows 和 Linux 出现问题时，先保存 `driver-monitor-doctor --json` 的完整结果；
- Windows、CUDA、摄像头和准确率都必须有真实输出，不能仅凭代码推断已经成功。

## 8. “迁移完成”的最低标准

只有同时满足以下条件，才能说某个平台迁移完成：

1. 从空环境按本文档安装成功；
2. 无摄像头环境诊断通过；
3. 单元测试通过；
4. 同一段视频可以完成推理并生成可读日志；
5. 摄像头可以启动、停止并被安全释放；
6. 若声称支持 NVIDIA GPU，诊断显示 `cuda:0` 且实际推理完成；
7. 已把平台、Python、依赖、设备、命令和已知问题写进实验记录。

Docker、云部署和 TensorRT 不属于当前这一步。先把 Windows/Linux 原生 CPU 基线和 NVIDIA 实机验收做稳，再进入部署阶段。
