# Workspace 导入说明

**不要导入 Main / OB1。** 对方工程通常已有主程序，覆盖后用户逻辑会丢。本仓库已删除 `Main.xml`。

## 推荐导入顺序

在 TIA **VCI / 工作区**中，按顺序拖到项目：

| 顺序 | 文件 | 拖到 |
|------|------|------|
| 1 | `UDT_DigSlot.xml` | PLC 数据类型 |
| 2 | `UDT_AnaSlot.xml` | PLC 数据类型 |
| 3 | `DB_IO_Config.xml` | 程序块（编号 **810**，取消优化访问） |
| 4 | `DB_IO_Runtime.xml` | 程序块（编号 **811**，取消优化访问） |
| 5 | **`FC_IO_Apply.scl`** | 程序块（**用 scl，不要用 xml**） |

然后：在对方**已有的 OB1 / Main** 里加一个网络，调用 `FC_IO_Apply`（写法见 `plc/scl/OB1_Call.scl`）。再 **编译 → 下载**。

## 关于 FC

- Openness 对 SCL 的 XML 语句格式要求极严，手写 XML 易报错（如 `The token is not supported`）。
- **请使用 `FC_IO_Apply.scl`**（已验证可成功导入）。
- 已不再提供 `FC_IO_Apply.xml` / `Main.xml`，避免误拖覆盖。

## 导入后检查

- DB810 / DB811：取消「优化的块访问」
- 现有 OB1 中已调用 `FC_IO_Apply`（不要用本仓库的 Main 覆盖对方主程序）
- CPU 已勾选 **允许来自远程对象的 PUT/GET 通信** 并重新下载
- Web 连接页：配置 DB = `810`，运行 DB = `811`（若对方工程已占用这两个号，在 TIA 改块号并同步改连接页）
