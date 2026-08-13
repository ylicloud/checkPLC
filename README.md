# checkPLC — PLC IO 通检

面向车间质检的 **S7-1200/1500 控制柜 IO 通道通检**工具。用浏览器配合 PLC 通检程序，检测 DI / DQ / AI / AQ 是否正常，无需制作 WinCC 画面。

| 通道 | 你做什么 | 界面反馈 |
|------|----------|----------|
| **DI** | 端子加 24V | 大字通道号 + 语音「通道十二」 |
| **AI** | 端子加电流 | 通道与毫安值 + 语音「通道一，四毫安」 |
| **DQ** | 点通道按钮强制高电平 | 万用表测端子电压 |
| **AQ** | 无需操作，PLC 自动出电流 | 第 1 路 4 mA … 第 8 路 11 mA，第 9 路再回 4 mA |

每类 IO 预留 **20 个模块槽**，勾选实际模块并填起始地址即可换柜，不必改 PLC 程序。

---

## 新笔记本：安装并运行

质检笔记本**不需要**安装 TIA Portal、WinCC 或数据库。柜配置存在本仓库 `configs/*.json`。

### 需要安装的软件

| 软件 | 要求 | 用途 |
|------|------|------|
| **Windows** | 10 / 11（64 位） | 操作系统 |
| **Python** | **3.10 或更高**（建议 3.11 / 3.12） | 运行 Web 后端 |
| **浏览器** | Chrome 或 Edge | 通检界面 |

1. 打开 https://www.python.org/downloads/ 下载 Windows 安装包。
2. 安装时**必须勾选** **Add python.exe to PATH**，再点 Install Now。
3. 装完后打开「命令提示符」或 PowerShell，输入 `python --version`，应看到 `Python 3.10` 或更高。若提示找不到命令，把 Python 重装一遍并勾选 PATH。

### 拿到本项目

任选一种：

- 把整个 `checkPLC` 文件夹拷到笔记本（例如 `D:\checkPLC`），**不要只拷里面某几个文件**。
- 或已安装 Git 时：

```powershell
git clone git@github.com:ylicloud/checkPLC.git
cd checkPLC
```

后面步骤都在**项目根目录**执行（能看到 `setup.bat`、`run.bat` 的那一层）。

### 首次安装（只做一次）

1. 双击 **`setup.bat`**。
2. 等待创建虚拟环境 `.venv` 并安装依赖（首次约 1～3 分钟）。
3. 若询问是否生成语音词片，一般回车跳过即可（仓库已带 mp3）。
4. 看到 `Setup complete!` 即成功。

若双击被 Windows 拦截：点「更多信息」→「仍要运行」。`setup.bat` 会自动用 Bypass 策略调用 PowerShell，一般不必改系统执行策略。

PowerShell 里手动安装时，必须加 `.\` 前缀：

```powershell
cd D:\checkPLC
.\scripts\setup.ps1
```

### 每次通检：启动

1. 双击 **`run.bat`**。
2. 会弹出黑色命令行窗口，并自动打开浏览器。
3. 若没自动打开，手动访问：**http://127.0.0.1:8000**
4. 右上角应显示「未连接」。顶栏有：连接 / 配置 / DI / AI / DQ / AQ。

**不要关掉那个黑色窗口**，关掉等于停止服务。要停止时：在窗口里按 `Ctrl+C`，或直接关闭窗口。

### 第一次验证（无需 PLC，约 3 分钟）

用来确认本机安装成功、界面和语音可用。

1. 打开浏览器后，先**随便点一下页面**（浏览器默认禁止自动出声）。
2. **连接**页：保持勾选「Mock 模式」→ 点 **连接**。右上角变为「已连接 (Mock)」。
3. **配置**页：在列表里点 `example_cabinet`（或双击）→ 点 **加载** → 再点 **保存并下发**。
4. **DI** 页：点 **模拟通道1 上升沿**。应出现大字通道号，并听到语音。
5. **AI** 页：点 **模拟通道1 ≈5mA**，应显示毫安并播报。

以上都正常，说明本机已可使用。下一步按「界面怎么用」做真柜通检，或继续用 Mock 熟悉各页。

### 安装或启动失败时

| 现象 | 处理 |
|------|------|
| `Python not found` / `3.10+ required` | 重装 Python 3.10+，勾选 Add to PATH，新开一个命令行再试 |
| `ERROR: .venv not found` | 先双击 `setup.bat`，再双击 `run.bat` |
| 浏览器打不开或页面空白 | 看黑色窗口是否还在跑；手动打开 http://127.0.0.1:8000 |
| 端口被占用 | 关掉其它占用 8000 的程序，或关掉上一次没关干净的 `run.bat` 窗口后再启动 |
| 提示 snap7 未就绪 | Mock 仍可用；真机通检需 `setup.bat` 成功装上 `python-snap7` |
| 没有声音 | 先点击页面任意处；检查系统音量；连接页可把语音速度调到 1× |

---

## 界面怎么用

启动后按顶栏从左到右操作。真机通检建议顺序：**连接 → 配置 → DI → AI → DQ → AQ**。

### 1. 连接

| 项 | 说明 |
|----|------|
| **Mock 模式** | 勾选：不连真实 PLC，用页面上的「模拟」按钮练手。取消：连现场 CPU。 |
| **IP** | CPU 的 IPv4，例如 `192.168.0.1`。须与笔记本同一网段。 |
| **机架 / 槽位** | S7-1200/1500 一般是机架 `0`、槽位 `1`。 |
| **配置 DB / 运行 DB** | 默认 `10` / `11`，须与 TIA 里通检 DB 编号一致。 |
| **语音速度** | 1×～2×。新的播报会打断旧的，不排队。 |

点 **连接**。成功后右上角为「已连接」或「已连接 (Mock)」。点 **断开** 会清掉 DQ 强制再断开。

连真实 PLC 失败时，常见原因见下文「连接真实 PLC」。

### 2. 配置

告诉程序这台柜子有哪些模块、过程映像从哪个字节开始。每类最多 20 槽，**只勾选实际存在的模块**。

1. 在「已保存的配置」里**单击选中**，再点 **加载**（或**双击**直接加载）。
2. 用「DI 槽 / DQ 槽 / AI 槽 / AQ 槽」切换编辑哪一类。
3. 每个槽勾选左侧 **启用**，填写：

   | 字段 | 含义 | 例子 |
   |------|------|------|
   | 名称 | 方便辨认，可空 | `DI16_本机` |
   | 起始字节 | TIA 自动分配的过程映像字节，**不要改硬件地址** | `%I0.0` → `0`；`%IW64` → `64` |
   | 通道数 | 该模块点数 | DI/DQ 常见 8/16/32；AI/AQ 常见 4/8 |
   | Raw满 / 下限mA / 上限mA | 仅 AI/AQ | 默认 0～27648 对应 4～20 mA |

4. 下方「IO 地址一览」会按起始字节 + 通道推出地址范围，请与 TIA **设备视图**对照。
5. 在「配置名」里起名（如 `用户A_标准柜`）→ 点 **保存并下发**。
   - 会写入 `configs/用户A_标准柜.json`。
   - 若当前已连接 PLC，同时把配置下发到 DB10。
   - 未连接时只保存到本机，连上后再保存一次即可下发。

下次测同类型柜子：加载已有配置，通常只改连接页的 IP。点 **刷新列表** 可重新扫描 `configs` 目录。

没有现成 JSON 时：可从空白槽位手工填，或在工程机上从 Portal 导出（见后文）。

### 3. DI（数字量输入）

1. 先完成连接，并已加载、保存过带启用 DI 槽的配置。
2. 给对应端子加 **24V**。
3. 页面大字显示**该模块内**通道号（1…N，不跨模块累加），并语音播报。
4. 「通道一览」里可看每个点的地址和当前状态。

Mock：点 **模拟通道1 上升沿**。真机连接时该按钮不可用。

### 4. AI（模拟量输入）

1. 连接后程序会记一版**空载初始值**（没接信号笔时的读数）。
2. 用信号发生器/电流笔给该通道加电流。
3. 满足下面条件才播报，避免拔笔回落、抖动误报：
   - 相对空载有明显变化（约 **10%**）
   - 数值稳定约 **0.3 秒**
   - 两次播报间隔至少 **1 秒**
   - 回到接近空载（拔笔）不再播
4. 语音类似「通道一，四毫安」。超过 24 mA 会播「超出二十四毫安」。

Mock：点 **模拟通道1 ≈5mA**。

### 5. DQ（数字量输出）

1. 左侧列表选中要测的 DQ 模块。
2. 点击 1～32 通道按钮：该点强制为高电平，按钮变绿，并播报通道号。
3. 用万用表测对应端子是否有 24V。
4. **复位本槽** / **全部复位** 清掉强制。

真机必须已把通检程序（含 `FC_IO_Apply`、非优化的 DB10/DB11）下载到 CPU，否则按钮变绿但端子没电。Mock 下变绿即表示强制逻辑成功。

### 6. AQ（模拟量输出）

本页只监视，**不用点按钮**。PLC 按通道序号输出 **4～11 mA 循环**阶梯电流（第 1 路 4 mA，第 2 路 5 mA … 第 8 路 11 mA，第 9 路再从 4 mA 起）。用电流表测端子，对照表中的「设定 mA」。

同样需要已下载通检程序。

### 语音

- 播的是预录 **mp3** 词片；没有词片时回退浏览器 TTS。
- 通道号按**模块内** 1…N；大于 20 简化读音（21 →「二一」）。
- 第一次请先点击页面，否则浏览器会拦截声音。
- 顶栏 **帮助** 里有「通检流程 / 语音」等说明。

---

## 连接真实 PLC（现场通检）

### 网络

- 笔记本网口与 PLC **同一网段**（例如都是 `192.168.0.x`）。
- Windows 防火墙放行 **TCP 102**（S7 通信）。
- 连接页取消 Mock，填 CPU IP，机架 0、槽位 1，再点连接。

### PLC 侧（工程机上事先做好）

完整步骤见 [docs/tia-import.md](docs/tia-import.md)。摘要：

1. 在 TIA 中按用户柜组态硬件（CPU、本机模块、ET200SP 等），**不要为了通检去改自动分配的地址**。
2. 按 [workspace/README_IMPORT.md](workspace/README_IMPORT.md) 导入通检 UDT、DB10/DB11、`FC_IO_Apply.scl`、OB1。
3. DB10 / DB11 取消「优化的块访问」。
4. CPU：**保护与安全 → 连接机制** 勾选 **允许来自远程对象的 PUT/GET 通信**（S7-1200 必做）。访问级别不要设成「完全保护」，否则勾选框是灰的。
5. 重新下载**硬件 + 程序**。

### Web 侧

1. 连接页：取消 Mock，填 IP → 连接。
2. 配置页：加载或填写本柜模块 → **保存并下发**。
3. 建议先只启用本机 DI 做通电确认，再逐步启用 AI / DQ / AQ。
4. 按 DI → AI → DQ → AQ 逐通道检测。

### 通检结束后

下载用户**正式程序**，不要把通检 DB/SCL 带到出厂柜子上。

### 真机连不上时

| 报错 / 现象 | 常见原因 |
|-------------|----------|
| `class=0x81, code=0x04` 或 PUT/GET | 未勾选 PUT/GET，或改完没重新下载 |
| `Invalid address 0x05` | DB 仍是优化访问、块编号不是 10/11、或未下载到 CPU |
| 能连上但 DI 无反应 | 配置起始字节与 TIA 不一致，或该槽未勾选「启用」 |
| DQ 按钮绿、端子没电 | 未下载 `FC_IO_Apply`，或 DB11 写失败 |

---

## 从 Portal 自动读取模块地址（可选）

免去在配置页手工抄地址。这是**工程机**上的步骤；质检笔记本只需拿到生成的 `configs/柜名.json`。

自动导出支持 **TIA Portal V20 和 V21**（不是只支持 V21，也不支持未升级的 V15～V19 工程直接读）。

**推荐做法：先在 Portal 里打开目标工程（PLC 离线），再跑导出。**  
工具会附加到**正在运行的 TIA**，读取当前已打开的工程，**不必把工程文件夹路径交给它**。同一 Portal 请只开目标工程（它取第一个已打开工程）。

工程机前置：TIA V20 或 V21（含 Openness）；当前 Windows 用户加入组 **Siemens TIA Openness** 后重新登录；安装 [.NET SDK](https://dotnet.microsoft.com/download)。

```bat
REM 1) 已在 Portal 中打开工程，PLC 离线
cd tools\tia-openness-export
export.bat --out D:\Temp\柜A.aml

REM 2) 转成 Web 配置（在项目根目录）
cd ..\..
python scripts\aml_to_cabinet.py D:\Temp\柜A.aml -o configs\柜A.json --name 柜A --ip 192.168.0.1
```

成功时命令行会出现「附加到已运行的 TIA Portal」。然后在 Web **配置**页加载 `柜A`。

Portal 没开时的备选（较慢）：指定 `.ap20` / `.ap21` **文件**（不是文件夹），并加 `--new`：

```bat
export.bat --project "D:\path\质检查线.ap21" --out D:\Temp\柜A.aml --new
```

只导出某一站：`export.bat --device "S7-1200 station" --out D:\Temp\柜A.aml`

更细的映射规则见 [docs/tia-openness-export.md](docs/tia-openness-export.md)、[tools/tia-openness-export/README.md](tools/tia-openness-export/README.md)。

无 Portal 时可用仓库示例验证转换脚本：

```bat
python scripts\aml_to_cabinet.py tools\tia-openness-export\samples\demo_cabinet.aml -o configs\demo_from_aml.json --name demo_from_aml
```

---

## 通检全流程（对照）

```
TIA 组态硬件 →（可选）打开工程后 export.bat → aml_to_cabinet 生成 JSON
       ↓
导入通检程序 → 允许 PUT/GET → 下载到 CPU
       ↓
笔记本：setup.bat（仅首次）→ run.bat → 浏览器
       ↓
连接（真机取消 Mock）→ 加载柜配置 → 保存并下发
       ↓
DI / AI（听语音）→ DQ（点按钮测端子）→ AQ（测阶梯电流）
       ↓
下载用户正式程序，恢复出厂状态
```

---

## 技术说明（可选阅读）

```
用户柜 CPU/IO  ←── S7 (snap7) ──→  Web 后端 (FastAPI)  ←── HTTP ──→  浏览器
                      ↑
              TIA 下载的通检 DB + SCL
```

- **DI / AI**：Web 周期读过程映像 I / IW，检测上升沿或电流变化后显示并播报。
- **DQ**：Web 写 `DB_IO_Runtime` 强制位 → PLC OB1 周期写到 Q。
- **AQ**：PLC 按通道输出 4～11 mA 循环，Web 只读监视。

| 组件 | 技术 |
|------|------|
| Web 后端 | Python 3.10+、FastAPI、uvicorn |
| PLC 通信 | python-snap7（S7，TCP 102） |
| 前端 | 原生 HTML / CSS / JavaScript |
| PLC 程序 | SCL；导入用 Openness XML（`workspace/` 为 V20，V21 一般可导入） |

### 其它脚本

| 脚本 | 作用 |
|------|------|
| `scripts/generate_wavs.py` | 重新生成语音 mp3（需先 `pip install edge-tts`） |
| `scripts/build_workspace_xml.py` | 重新生成 `workspace/` 下 UDT/DB/Main 的 Openness XML |

### 项目结构

```
checkPLC/
├── setup.bat / run.bat   # 一键安装、一键启动
├── configs/              # 每柜 JSON
├── docs/                 # 设计、TIA 导入、Openness 导出、更新说明
├── plc/                  # PLC 源程序（UDT / DB / SCL）
├── workspace/            # 可拖入 TIA 的 Openness XML
├── web/                  # FastAPI + 浏览器界面
├── tools/tia-openness-export/   # 从 Portal V20/V21 导出 AML
└── scripts/              # setup / run / AML 转换 / 语音
```

| 文档 | 内容 |
|------|------|
| [docs/更新说明.md](docs/更新说明.md) | 版本升级记录 |
| [docs/tia-import.md](docs/tia-import.md) | 通检程序导入与 PUT/GET |
| [docs/tia-openness-export.md](docs/tia-openness-export.md) | 从 Portal 导出地址 |
| [docs/design.md](docs/design.md) | 架构与数据块布局 |
| [plc/README.md](plc/README.md) | PLC 程序与字节偏移 |
| [workspace/README_IMPORT.md](workspace/README_IMPORT.md) | VCI 导入顺序 |

---

## 许可证

本项目为内部质检工具，版权归 ylicloud 所有。
