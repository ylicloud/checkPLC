# TIA Portal 导入与通信设置

适用于 TIA Portal V20、S7-1200/1500。

## 1. 硬件组态

1. 打开工程「质检查线」（或复制为每柜工程）。
2. 按用户柜添加 CPU、本机 DI/DQ/AI/AQ、ET200SP 等。
3. 记下各模块过程映像起始地址（设备视图或默认变量表），例如：
   - DI16：`%I0.0` → 起始字节 `0`，通道数 `16`
   - DQ16：`%Q0.0` → 起始字节 `0`，通道数 `16`
   - AI8：首通道 `%IW64` → 起始字节 `64`，通道数 `8`
   - AQ4：首通道 `%QW80` → 起始字节 `80`，通道数 `4`

**不要为了通检去改自动分配的地址**，只需把地址填进 Web 配置。

## 2. 导入程序（推荐：workspace Openness XML）

仓库 [`workspace/`](../workspace/) 已生成可导入的 Openness XML（V20）：

| 文件 | 导入到 |
|------|--------|
| `UDT_DigSlot.xml` / `UDT_AnaSlot.xml` | PLC 数据类型 |
| `DB_IO_Config.xml` / `DB_IO_Runtime.xml` | 程序块（DB10/DB11，非优化） |
| **`FC_IO_Apply.scl`** | 程序块（**必须用 scl**；手写 xml 会报 token 错误） |
| `Main.xml` | OB1（含调用 FC） |

在 Portal **VCI 工作区**中按 [`workspace/README_IMPORT.md`](../workspace/README_IMPORT.md) 的顺序拖入项目，再编译下载。

重新生成 UDT/DB/Main XML：

```bash
python scripts/build_workspace_xml.py
```

（脚本不再生成 `FC_IO_Apply.xml`，FC 请始终用 `workspace/FC_IO_Apply.scl`。）

### 备选：手工 SCL

1. 添加 SCL 块，粘贴 `plc/` 下源文件。
2. DB 取消「优化的块访问」。

## 3. 允许 Web 用 S7 访问（S7-1200 必做，否则报 0x81/0x04）

在 CPU 属性中（TIA Portal）：

1. **保护与安全 → 访问级别**：不要选「不能访问（完全保护）」。  
   通检建议选 **完全访问权限（无保护）** 或至少「读访问 / HMI 访问」。  
   → 若 PUT/GET 勾选框是**灰色**，几乎都是因为当前为「完全保护」；先改访问级别，勾选框才会可点。
2. **保护与安全 → 连接机制**：勾选 **允许来自远程对象的 PUT/GET 通信**。
3. 较新固件若启用了用户管理：确保 **Anonymous（匿名）** 用户存在，且具备读/写或 HMI 权限（官方要求，否则 PUT/GET 仍不可用）。
4. 改完后必须 **重新下载硬件+程序** 到 PLC。
5. PC 与 PLC 同网段，防火墙放行 TCP **102**。Web：机架 `0`、槽位 `1`，取消 Mock。

报错 `class=0x81, code=0x04` → 多为未勾选 PUT/GET 或未重新下载。

## 4. 验证

1. 启动 Web（见根目录 `README.md`）。
2. 配置页先只启用本机 DI（起始字节 0），AI/AQ 先全部取消启用，避免读到不存在的地址。
3. 连接成功后，给 DI 端子 24V，应大字+语音。
4. DQ/AQ 需已导入 DB10/DB11（非优化）+ `FC_IO_Apply` 并下载后再测。
5. AQ 在 4～20mA 组态下，通道应为 4、5、6… mA。

## 5. 通检结束后

下载用户正式程序前，确认通检程序已替换或 CPU 已恢复正式工程，避免误带 DQ/AQ 测试逻辑出厂。
