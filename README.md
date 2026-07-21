# PLC IO 通检 Portal

车间控制柜 DI/DQ/AI/AQ 通道通检：**浏览器 Web 界面** + **S7（snap7）** + **可导入 TIA 的通检程序**。无需制作 WinCC 画面。

## 功能

| 通道 | 行为 |
|------|------|
| DI | 24V 上升沿 → 大字通道号 + 语音「通道十二」 |
| AI | 电流变化 → 显示 + 语音「通道一，四毫安」 |
| DQ | 选模块后点 1～32 按钮强制高电平 |
| AQ | PLC 自动输出 4、5、6… mA（通道 n → 3+n mA） |

每类模块预留 **20 个槽**，配置页勾选实际数量即可，不必改程序。

## 快速开始（Mock，无需 PLC）

```bash
cd d:\repos\TestPLC
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn web.app.main:app --host 127.0.0.1 --port 8000
```

浏览器打开 http://127.0.0.1:8000  

1. **连接**页保持「Mock 模式」→ 连接  
2. **配置**页加载 `example_cabinet` → 保存  
3. **DI** 页点「模拟 DI 通道1 上升沿」听语音（无 WAV 时用浏览器 TTS）

可选生成低延迟词片：

```bash
pip install edge-tts
python scripts/generate_wavs.py
```

## 连接真实 PLC

1. 按 [docs/tia-import.md](docs/tia-import.md) 导入 `plc/` 程序，允许 PUT/GET，下载  
2. 取消 Mock，填写 CPU IP，连接  
3. 配置页勾选模块并填写 **组态自动生成的起始字节地址**（不要改硬件地址）  
4. 保存并下发 → 开始通检  

设计说明见 [docs/design.md](docs/design.md)。

## 目录

```
configs/          每柜 JSON 配置
docs/             设计与 TIA 导入说明
plc/              UDT / DB / SCL 源
workspace/        TIA VCI Openness XML（可拖入工程）
web/              FastAPI + 前端
scripts/          语音词片 / 生成 workspace XML
```
