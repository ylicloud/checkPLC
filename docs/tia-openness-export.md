# 用 TIA Openness（V20）导出硬件 → 导入 checkPLC Web

目标：从 Portal 工程自动得到 `configs/柜名.json`，避免在 Web 页面手工抄模块地址。

## 总流程

```
TIA V20 打开工程（PLC 离线）
        ↓
tools/tia-openness-export  →  xxx.aml
        ↓
scripts/aml_to_cabinet.py  →  configs/柜名.json
        ↓
Web「配置」页加载柜名 → 连接通检
```

## 1. 导出 AML（工程机，需装 TIA V20）

详见 [`tools/tia-openness-export/README.md`](../tools/tia-openness-export/README.md)。

```bat
cd tools\tia-openness-export
export.bat --out D:\Temp\柜A.aml
```

或只导出某一站：

```bat
export.bat --device "S7-1200 station" --out D:\Temp\柜A.aml
```

也可用 Portal UI：设备视图中右键站 → **导出 CAx**（若菜单可用）。

## 2. 转为柜配置 JSON

在仓库根目录（质检笔记本也可，只需 AML 文件）：

```bat
python scripts\aml_to_cabinet.py D:\Temp\柜A.aml -o configs\柜A.json --name 柜A --ip 192.168.0.1
```

无真实 AML 时可先用仓库内示例验证转换脚本：

```bat
python scripts\aml_to_cabinet.py tools\tia-openness-export\samples\demo_cabinet.aml -o configs\demo_from_aml.json --name demo_from_aml --dry-run
```

## 3. Web 加载

1. 启动 `run.bat` / `.\scripts\run.ps1`
2. 「配置」页下拉选择 `柜A` → **加载**
3. 核对地址一览与 TIA 设备视图一致后，**保存并下发**（可选，写入本机 configs 并下发 DB）

## AML → JSON 映射规则

| AML | Web JSON |
|-----|----------|
| Digital + Input | `di[]` |
| Digital + Output | `dq[]` |
| Analog + Input | `ai[]`（`start_addr` = 字节，如 IW64→64） |
| Analog + Output | `aq[]` |
| `StartAddress` | `start_addr` |
| 通道 Number 最大值+1 或 Length | `channel_count` |
| 模块名 | `name` |
| 按起始地址排序 | 逻辑 `slot` 1…20（每类最多 20） |

本机集成 DI/DQ 同一物理模块会拆成 `di` + `dq` 两个逻辑槽。

## 注意

- CAx 要求 PLC **离线** 导出
- `Length=0` / `StartAddress=-1` 的地址官方不导出
- 真实 CAx AML 的命名空间可能与示例不同；若解析为 0 个模块，把 AML 样例发回以便适配
- IP 优先用 `--ip`；脚本也会尝试从 AML 猜 IPv4
- JSON 中 `_import.modules_found` 为追溯信息，不影响 Web 扫描

## 相关链接

- Siemens： [Export of CAx data (V20)](https://docs.tia.siemens.cloud/r/en-us/v20/tia-portal-openness-api-for-automation-of-engineering-workflows/export/import/importing/exporting-hardware-data/export-of-cax-data)
- 本仓库通检程序导入： [tia-import.md](tia-import.md)
