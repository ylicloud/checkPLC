# CheckPLC · TIA Openness CAx 导出工具（V20 / V21）

将 Portal 工程中的 **PLC / IO 模块组态与过程映像地址** 导出为 AML，再经仓库根目录脚本转为 Web 可用的 `configs/*.json`。

## 前置条件

1. 安装 **TIA Portal V20 或 V21**（含 Openness）
2. Windows 用户加入组 **Siemens TIA Openness**（或对 exe 做 Openness 证书签名）
3. 安装 [.NET SDK](https://dotnet.microsoft.com/download)（用于 `dotnet build`，目标框架 net48）
4. 确认 PublicAPI 路径存在（本机优先 V21）：

```
V21: C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48\Siemens.Engineering.Base.dll
V20: C:\Program Files\Siemens\Automation\Portal V20\PublicAPI\V20\Siemens.Engineering.dll
```

若路径不同，设置环境变量：

```bat
set TIA_PUBLICAPI=C:\Program Files\Siemens\Automation\Portal V21\PublicAPI\V21\net48
```

## 编译

```bat
cd tools\tia-openness-export
export.bat --help
```

或：

```bat
dotnet build -c Release
```

## 导出 AML

**推荐**：先在 Portal 中打开目标工程，再附加导出：

```bat
export.bat --out D:\Temp\柜A.aml
```

指定工程文件（无已打开实例时）：

```bat
export.bat --project "D:\path\to\工程.ap21" --out D:\Temp\柜A.aml --new
```

只导出某一站：

```bat
export.bat --device "S7-1200 station" --out D:\Temp\柜A.aml
```

## 转为 Web 配置

在仓库根目录：

```bat
python scripts\aml_to_cabinet.py D:\Temp\柜A.aml -o configs\柜A.json --name 柜A --ip 192.168.0.1
```

然后启动 Web，在「配置」页加载 `柜A`。

## 说明

- CAx 导出要求 PLC **离线**
- 导出内容含模块地址（`StartAddress` / `Length` / `IoType`）与通道信息
- 本机集成 DI/DQ 会拆成 Web 配置中的 `di` / `dq` 两个逻辑槽
- IP 若 AML 中读不到，用 `--ip` 手工指定
- V21 Openness 将 API 拆到 `Siemens.Engineering.Base` + `Siemens.Engineering.Step7`；`export.bat` 会自动探测
