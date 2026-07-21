# Workspace 导入说明

## 推荐导入顺序

在 TIA **VCI / 工作区**中，按顺序拖到项目：

| 顺序 | 文件 | 拖到 |
|------|------|------|
| 1 | `UDT_DigSlot.xml` | PLC 数据类型 |
| 2 | `UDT_AnaSlot.xml` | PLC 数据类型 |
| 3 | `DB_IO_Config.xml` | 程序块 |
| 4 | `DB_IO_Runtime.xml` | 程序块 |
| 5 | **`FC_IO_Apply.scl`** | 程序块（**用 scl，不要用 xml**） |
| 6 | `Main.xml` | 程序块（OB1，调用 FC） |

然后：**编译 → 下载**。

## 关于 FC

- Openness 对 SCL 的 XML 语句格式要求极严，手写 XML 易报错（如 `The token is not supported`）。
- **请使用 `FC_IO_Apply.scl`**（你已验证可成功导入）。
- 已不再提供 `FC_IO_Apply.xml`，避免误拖。

## 导入后检查

- DB10 / DB11：取消「优化的块访问」
- OB1（Main）中已调用 `FC_IO_Apply`；若 Main 未覆盖成功，在 OB1 里手工加一次调用
- CPU 已勾选 PUT/GET 并重新下载
