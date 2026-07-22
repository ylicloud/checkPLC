# checkPLC — PLC IO 通检 Portal

面向车间质检场景的 **S7-1200/1500 控制柜 IO 通道通检**工具。通过浏览器 Web 界面配合 PLC 通检程序，快速检测 DI / DQ / AI / AQ 各通道是否工作正常，无需制作 WinCC 画面。

## 功能概览

| 通道类型 | 检测方式 | 界面反馈 |
|----------|----------|----------|
| **DI**（数字量输入） | 端子施加 24V，检测上升沿 | 大字显示通道号 + 语音播报「通道十二」 |
| **AI**（模拟量输入） | 施加电流信号，检测数值变化 | 显示通道与毫安值 + 语音「通道一，四毫安」 |
| **DQ**（数字量输出） | 选择模块，点击 1～32 按钮强制高电平 | 端子万用表测量输出电压 |
| **AQ**（模拟量输出） | PLC 自动输出阶梯电流 | 通道 n 输出 `3+n` mA（通道 1→4 mA，通道 2→5 mA …） |

### 核心特性

- **通用兼容**：DI / DQ / AI / AQ 各预定义 **20 个模块槽位**，勾选实际模块并填写地址即可，无需修改 PLC 程序
- **多柜配置**：每套控制柜保存独立 JSON 配置，换柜时只改配置
- **语音播报**：预录 WAV 词片拼接，毫秒级响应；缺失时自动回退浏览器 TTS
- **Mock 模式**：无真实 PLC 时可本地验证界面与语音
- **TIA 可导入**：提供 SCL 源文件与 VCI Openness XML，一键导入 TIA Portal V20

## 系统架构

```
用户柜 CPU/IO  ←── S7 (snap7) ──→  Web 后端 (FastAPI)  ←── HTTP ──→  浏览器
                      ↑
              TIA 下载的通检 DB + SCL
              （DQ 映到 Q，AQ 写阶梯电流）
```

- **DI / AI**：Web 周期读取过程映像 I / IW，检测上升沿或数值变化后触发显示与语音
- **DQ**：Web 写入 `DB_IO_Runtime` 强制位 → PLC OB1 周期写到 Q 区
- **AQ**：PLC 按全局通道号自动输出阶梯电流，Web 只读监视

## 技术栈

| 组件 | 技术 |
|------|------|
| Web 后端 | Python 3、FastAPI、uvicorn |
| PLC 通信 | python-snap7（S7 协议） |
| 前端 | 原生 HTML / CSS / JavaScript |
| PLC 程序 | SCL（S7-1200/1500）、TIA Portal V20 |

## 笔记本部署（质检现场）

### 需要安装的软件

| 软件 | 要求 | 用途 |
|------|------|------|
| **Windows** | 10 / 11（64 位） | 操作系统 |
| **Python** | 3.10 或更高（建议 3.11） | 运行 Web 后端 |
| **浏览器** | Chrome / Edge | 打开通检界面 |

安装 Python 时务必勾选 **「Add python.exe to PATH」**。下载：https://www.python.org/downloads/

**不需要**在质检笔记本上安装 TIA Portal、WinCC 或数据库——配置保存在本地 `configs/*.json` 文件中。

连接真实 PLC 时，笔记本网口需与 PLC **同一网段**，防火墙放行 **TCP 102**。

### 一键安装与启动

| 文件 | 作用 |
|------|------|
| **`setup.bat`** | 首次运行：创建虚拟环境、安装依赖、可选生成语音词片 |
| **`run.bat`** | 每次通检：启动 Web 服务并打开浏览器 |

```
1. 安装 Python 3.10+（勾选 Add to PATH）
2. 拷贝或 git clone 整个 checkPLC 文件夹
3. 双击 setup.bat          ← 仅首次
4. 双击 run.bat            ← 每次通检
5. 浏览器打开 http://127.0.0.1:8000
```

PowerShell 手动执行时须加 `.\` 前缀（不能直接输入脚本名）：

```powershell
cd D:\repos\checkPLC
.\scripts\setup.ps1    # 安装
.\scripts\run.ps1      # 启动
```

### 配置归档与复用

每套控制柜在 Web **「配置」** 页填写模块信息后，输入配置名（如 `用户A_标准柜`）点 **「保存并下发」**，即归档为 `configs/用户A_标准柜.json`。

下次检测同类型柜子：下拉加载已有配置，通常只需修改 PLC IP 即可开始通检。可与 TIA 工程归档一一对应管理。

### 从 TIA Openness 自动生成柜配置（可选）

工程机安装 TIA V20 后，可用 Openness 导出硬件 AML，再转成 Web 配置，免手工抄地址。完整说明见 [docs/tia-openness-export.md](docs/tia-openness-export.md)。

```bat
cd tools\tia-openness-export
export.bat --out D:\Temp\柜A.aml

cd ..\..
python scripts\aml_to_cabinet.py D:\Temp\柜A.aml -o configs\柜A.json --name 柜A --ip 192.168.0.1
```

## 工具使用

### 日常运行（质检笔记本）

| 工具 | 命令 / 操作 | 说明 |
|------|-------------|------|
| 安装环境 | 双击 `setup.bat` 或 `.\scripts\setup.ps1` | 创建 `.venv`、安装依赖 |
| 启动 Web | 双击 `run.bat` 或 `.\scripts\run.ps1` | 打开 http://127.0.0.1:8000 |
| 生成语音词片 | `python scripts/generate_wavs.py` | 需先 `pip install edge-tts`；降低 DI/AI 播报延迟 |

### 从 Portal 导出柜配置（工程机，需 TIA V20）

免去在 Web 页面手工填写模块起始地址。

**前置：**

1. 安装 TIA Portal V20（含 Openness）
2. Windows 用户加入组 **Siemens TIA Openness**
3. 安装 .NET SDK（用于编译导出工具）
4. 确认 DLL 存在（路径不同时设置环境变量 `TIA_PUBLICAPI`）：

```
C:\Program Files\Siemens\Automation\Portal V20\PublicAPI\V20\Siemens.Engineering.dll
```

**步骤：**

```bat
REM 1) 建议先在 Portal 中打开目标工程（PLC 离线）
cd tools\tia-openness-export

REM 2) 编译并导出 AML（首次会 dotnet build）
export.bat --out D:\Temp\柜A.aml

REM 也可指定工程文件 / 只导出某一站：
REM export.bat --project "D:\path\质检查线.ap20" --out D:\Temp\柜A.aml --new
REM export.bat --device "S7-1200 station" --out D:\Temp\柜A.aml

REM 3) 转为 Web 可用的 configs JSON（在仓库根目录）
cd ..\..
python scripts\aml_to_cabinet.py D:\Temp\柜A.aml -o configs\柜A.json --name 柜A --ip 192.168.0.1
```

**无 Portal 时验证转换脚本**（使用仓库内示例 AML）：

```bat
python scripts\aml_to_cabinet.py tools\tia-openness-export\samples\demo_cabinet.aml -o configs\demo_from_aml.json --name demo_from_aml
```

然后在 Web **配置**页加载对应配置名即可。

| 工具 | 路径 | 作用 |
|------|------|------|
| CAx 导出 | `tools/tia-openness-export/` | Openness 导出硬件 → `.aml` |
| AML 转换 | `scripts/aml_to_cabinet.py` | `.aml` → `configs/*.json` |
| 说明文档 | `docs/tia-openness-export.md` | 映射规则与注意事项 |

### 其它脚本

| 脚本 | 作用 |
|------|------|
| `scripts/build_workspace_xml.py` | 重新生成 `workspace/` 下 UDT/DB/Main 的 Openness XML |
| `scripts/generate_wavs.py` | 生成中文语音词片到 `web/frontend/assets/voice/` |

## 快速开始（Mock 模式，无需 PLC）

```bash
git clone git@github.com:ylicloud/checkPLC.git
cd checkPLC

python -m venv .venv
.\.venv\Scripts\activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

uvicorn web.app.main:app --host 127.0.0.1 --port 8000
```

浏览器打开 http://127.0.0.1:8000

1. **连接**页：保持勾选「Mock 模式」→ 点击连接
2. **配置**页：加载 `example_cabinet` → 保存并下发
3. **DI** 页：点击「模拟 DI 通道 1 上升沿」，验证大字显示与语音播报

### 生成语音词片（可选）

```bash
pip install edge-tts
python scripts/generate_wavs.py
```

词片输出到 `web/frontend/assets/voice/`，可显著降低播报延迟。

## 连接真实 PLC

### 1. 导入通检程序

按 [docs/tia-import.md](docs/tia-import.md) 将 `plc/` 或 `workspace/` 中的程序导入 TIA Portal，编译并下载到 PLC。

简要步骤：

1. 在 TIA 中组态用户柜硬件（CPU、本机模块、ET200SP 等）
2. 导入 UDT、DB10/DB11、`FC_IO_Apply`、OB1 调用
3. CPU 属性中允许 **PUT/GET 通信**（S7-1200 必做）
4. 重新下载硬件与程序

### 2. 配置并通检

1. Web **连接**页：取消 Mock，填写 CPU IP（机架 0、槽位 1）
2. **配置**页：勾选实际 IO 模块，填写 TIA 自动分配的起始字节地址
3. 保存并下发配置到 PLC
4. 按 DI → AI → DQ → AQ 顺序逐通道检测

> **注意**：起始地址使用 TIA 组态自动生成的过程映像字节地址（如 `%I0.0` → 起始字节 `0`），不要手动修改硬件地址。

## 配置说明

每类 IO 最多 **20 个槽位**，每个槽位包含：

| 字段 | 说明 |
|------|------|
| `enable` | 是否启用该槽位 |
| `start_addr` | 过程映像起始字节地址 |
| `channel_count` | 通道数（每模块 4～32，常见 DI/DQ：8/16/32；AI/AQ：4/8） |
| `raw_full` / `eng_min_ma` / `eng_full_ma` | 仅 AI/AQ，默认 4～20 mA ↔ 0～27648 |

全局通道号按槽位 1→20、槽内通道顺序连续编号。示例配置见 [configs/example_cabinet.json](configs/example_cabinet.json)。

## 项目结构

```
checkPLC/
├── setup.bat             # 一键安装环境（Windows）
├── run.bat               # 一键启动服务
├── configs/              # 每柜 JSON 配置
├── docs/                 # 需求、设计、TIA 导入 / Openness 导出说明
│   ├── requirement.md
│   ├── design.md
│   ├── tia-import.md
│   └── tia-openness-export.md
├── plc/                  # PLC 源程序（UDT / DB / SCL）
│   ├── udt/
│   ├── db/
│   └── scl/
├── workspace/            # TIA VCI Openness XML（可拖入工程）
├── web/
│   ├── app/              # FastAPI 后端
│   └── frontend/         # 浏览器前端
├── tools/
│   └── tia-openness-export/  # TIA V20 CAx 导出 AML（export.bat）
├── scripts/
│   ├── setup.ps1 / run.ps1   # 环境安装与启动
│   ├── aml_to_cabinet.py     # AML → 柜配置 JSON
│   ├── generate_wavs.py      # 语音词片
│   └── build_workspace_xml.py
└── requirements.txt
```

## 文档索引

| 文档 | 内容 |
|------|------|
| [docs/design.md](docs/design.md) | 架构设计与数据块布局 |
| [docs/tia-import.md](docs/tia-import.md) | TIA Portal 导入与通信设置 |
| [docs/tia-openness-export.md](docs/tia-openness-export.md) | Openness 导出硬件 → 柜配置 JSON |
| [plc/README.md](plc/README.md) | PLC 程序说明与字节偏移表 |
| [workspace/README_IMPORT.md](workspace/README_IMPORT.md) | VCI 工作区导入顺序 |

## 通检流程

```
TIA 组态硬件 →（可选）Openness 导出 AML → aml_to_cabinet 生成 JSON
       ↓
导入通检程序 → 允许 PUT/GET → 下载
       ↓
启动 Web → 加载柜配置 → 保存并下发
       ↓
通检 DI/AI（听语音）→ 通检 DQ（点按钮测端子）→ 通检 AQ（测阶梯电流）
       ↓
下载用户正式程序，恢复出厂状态
```

## 许可证

本项目为内部质检工具，版权归 ylicloud 所有。
