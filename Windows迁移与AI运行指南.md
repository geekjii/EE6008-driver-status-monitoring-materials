# Windows 迁移与 AI 运行指南

## 1. 当前能做什么

这个仓库目前只能帮助组员和 AI 理解课程、项目目标和现有方案，暂时没有可执行程序。任何 AI 在声称“已经运行成功”之前，都必须先补齐代码、依赖、模型和测试数据，并给出真实的命令输出。

## 2. 推荐平台

推荐配置：

- Windows 11 64 位
- WSL2，建议使用 Ubuntu 24.04 LTS
- Docker Desktop，并启用 WSL2 integration
- NVIDIA 显卡及支持 WSL 的 Windows 驱动
- Git

不建议直接在 Windows 原生 Python 环境中混装 CUDA、PyTorch、OpenCV 和 TensorRT。优先在 WSL2 中开发；完成后再决定是否制作 Windows 原生版本。

### Jetson 与 Windows PC 的区别

- Jetson 使用 ARM64 和 JetPack/L4T，镜像名称通常包含 `l4t`。
- Windows PC + RTX 显卡通常是 x86_64，不能使用 Jetson 的 `l4t-*` 镜像。
- Windows/WSL2 应选择官方 x86_64 CUDA 或 PyTorch 镜像，并固定具体版本和镜像摘要。

## 3. Windows 初次准备

在管理员 PowerShell 中：

```powershell
wsl --install -d Ubuntu-24.04
wsl --update
```

重启后安装 Docker Desktop，并在 Docker Desktop 设置中开启 WSL2 backend 和对应 Ubuntu 发行版的集成。

在 WSL2 中检查：

```bash
uname -m
nvidia-smi
docker version
docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu24.04 nvidia-smi
```

具体 CUDA、PyTorch 和 Ultralytics 版本应在真正编写代码时再次核对官方兼容关系，不要只复制旧项目中的版本。

## 4. 后续代码结构

AI 或开发者应按下面的结构新增代码，不要把代码混进课程资料目录：

```text
src/                 主程序与算法
tests/               自动化测试
configs/             可提交的配置文件
scripts/             训练、导出和验证脚本
docs/                技术说明与实验记录
assets/samples/      少量、已获授权的测试样例
Dockerfile           x86_64 Windows/WSL2 运行环境
docker-compose.yml   可选的摄像头或服务配置
requirements.lock    固定的 Python 依赖
```

数据集、模型权重和实验输出应放在 Git 忽略目录中，并在文档中说明如何获取和校验。

## 5. 最小基线要求

第一版至少应做到：

1. 接受本地视频文件输入；摄像头输入可以作为第二阶段。
2. 每一帧输出检测结果，并在视频上显示状态。
3. 使用真实时间戳或视频 FPS 计算持续时间，不能把“固定帧数”直接当成三秒。
4. 输出可复核的日志：时间、状态、置信度和报警原因。
5. 提供 CPU 模式，GPU 只作为加速选项。
6. 提供一个不依赖私人数据的最小测试样例。

## 6. 评估要求

- 数据必须按驾驶员划分训练集、验证集和测试集，避免同一个人同时出现在训练和测试中。
- 除准确率外，应报告 precision、recall、F1、误报率、漏报率、处理 FPS 和报警延迟。
- 分别测试白天、夜间、戴眼镜、侧脸、遮挡和不同摄像头距离。
- 明确“困倦”“分心”和“已经睡着”的定义，不能混为同一个标签。
- 所有最终数字都要能够追溯到脚本、配置、模型版本和数据划分。

## 7. DriveEye 参考项目注意事项

如果继续使用 DriveEye：

- 不要沿用不存在的 `nvcr.io/nvidia/l4t-ml:r36.4.0`。
- README 所称 YOLOv5 与训练代码使用的 YOLO11 不一致，必须统一。
- 补齐并固定 PyTorch、Ultralytics、OpenCV 和 ONNX/TensorRT 依赖。
- 修正 TensorRT 导出脚本的模型路径。
- 将基于固定 15 FPS 和连续 45 帧的判断改为基于时间的滑动窗口。
- 重新准备数据并独立复现实验，不要引用未复现的结果。

## 8. 完成标准

只有同时满足以下条件，AI 才能说“Windows 迁移完成”：

- 新电脑可以从空环境按文档安装。
- CPU 模式能够处理一段示例视频。
- NVIDIA GPU 模式通过容器内 `nvidia-smi` 和实际推理测试。
- 自动化测试通过。
- 同一模型在同一视频上能得到可重复结果。
- README 中列出已知限制、数据来源、模型来源和许可证。
