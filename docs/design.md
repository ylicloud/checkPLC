# IO 通检 Portal 设计说明

## 目标

质检工程师对接用户柜（S7-1200/1500 + 本机模块 / ET200SP），通检 DI / DQ / AI / AQ。界面为浏览器 Web，无需 WinCC 画面。

## 架构

```
用户柜 CPU/IO  ←S7(snap7)→  Web 后端(FastAPI)  ←HTTP/WS→  浏览器
                     ↑
              TIA 下载的通检 DB + SCL
              （DQ 映到 Q，AQ 写阶梯电流）
```

- **DI / AI**：Web 周期读过程映像 I / IW，上升沿或变化时大字显示 + WAV 语音
- **DQ**：Web 写 `DB_IO_Runtime` 强制位 → PLC OB1 写到 Q
- **AQ**：PLC 按通道序号写 `mA = 4 + ((n-1) MOD 8)`（4～11 mA 循环）

## 配置模型（各类型最多 20 槽）

每槽字段：

| 字段 | 含义 |
|------|------|
| `enable` | 是否启用（未启用不扫描） |
| `start_addr` | 过程映像起始**字节**地址（如 IB10 → 10，QW80 → 80） |
| `channel_count` | DI/DQ：8/16/32；AI/AQ：2/4/8 等 |
| `raw_full` / `eng_min_ma` / `eng_full_ma` | 仅 AI/AQ，默认 **4～20 mA ↔ 0～27648**（`eng_min=4`，`eng_full=20`） |

**全局通道号**：同类型按槽 1→20、槽内通道顺序连续编号。只勾选实际模块（如 5 个），其余 `enable=false`，无需改程序。

**地址策略**：TIA 组态自动生成的地址不要改；把起始字节抄进配置即可。

## PLC 数据块

| 块 | 建议编号 | 用途 |
|----|----------|------|
| `DB_IO_Config` | DB10 | 四类各 20 槽配置（非优化，供外部访问） |
| `DB_IO_Runtime` | DB11 | DQ 强制位、AQ 监视值等 |

详见 [`plc/README.md`](../plc/README.md) 与字节偏移表。

## Web 页面

1. **连接**：PLC IP、机架、槽位、DB 编号
2. **配置**：勾选槽位、填地址；保存 JSON +（可选）下发到 DB10
3. **DI / AI**：大字 + WAV 播报
4. **DQ**：选模块 → 最多 32 按钮；全部复位
5. **AQ**：只读显示各通道设定 mA

## 语音

默认预加载 `web/frontend/assets/voice/*.wav` 词片拼接（毫秒级）。缺失时回退浏览器 TTS。可用 `scripts/generate_wavs.py` 生成词片。

## 每柜流程

1. TIA 组态硬件 → 导入 `plc/` → 允许 PUT/GET → 下载  
2. 启动 Web → 浏览器打开 → 填 IP 与模块配置  
3. 通检 DI/AI/DQ，端子核对 AQ 阶梯电流  
4. 换柜：改硬件组态 + 改/换配置 JSON，不改 SCL  
