# PLC 通检程序（导入 TIA）

## 文件

| 文件 | 说明 |
|------|------|
| `udt/UDT_DigSlot.scl` | DI/DQ 槽位结构 |
| `udt/UDT_AnaSlot.scl` | AI/AQ 槽位结构（默认 4～20mA） |
| `db/DB_IO_Config.scl` | 配置 DB（建议编号 10） |
| `db/DB_IO_Runtime.scl` | 运行 DB（建议编号 11） |
| `scl/FC_IO_Apply.scl` | 每周期：DQ 强制→Q，AQ 阶梯电流→QW |
| `scl/OB1_Call.scl` | OB1 调用示例 |

## 字节偏移（非优化 DB，供 Web/snap7）

### DB_IO_Config（DB10）

每个 **DigSlot** 占 **8** 字节：

| 偏移 | 类型 | 字段 |
|------|------|------|
| +0 | Byte | Enable（0/1，对应 Bool 0.0） |
| +1 | Byte | 对齐填充 |
| +2 | UInt | StartAddr（大端） |
| +4 | USInt | ChannelCount |
| +5 | USInt | 保留 |
| **步长** | | **6 字节**（与 TIA Standard UDT 一致） |

每个 **AnaSlot** 占 **16** 字节：

| 偏移 | 类型 | 字段 |
|------|------|------|
| +0 | Byte | Enable |
| +1 | Byte | 保留 |
| +2 | UInt | StartAddr |
| +4 | USInt | ChannelCount |
| +5 | USInt | 保留 |
| +6 | Int | RawFull（默认 27648） |
| +8 | Real | EngMax_mA（默认 20.0） |
| +12 | Real | EngMin_mA（默认 4.0） |

整块布局：

| 区域 | 偏移 | 长度 |
|------|------|------|
| DI[1..20] | 0 | 120 |
| DQ[1..20] | 120 | 120 |
| AI[1..20] | 240 | 320 |
| AQ[1..20] | 560 | 320 |
| **总长** | | **880** |

### DB_IO_Runtime（DB11）

| 区域 | 偏移 | 长度 | 说明 |
|------|------|------|------|
| DQ_Force[1..20] | 0 | 80 | 每槽 4 字节位图，bit0=通道1 … |
| AQ_mA[1..160] | 80 | 640 | Real 数组，全局通道监视（Web 只读） |
| Heartbeat | 720 | 2 | UInt，OB1 自增 |
| **总长** | | **724**（对齐） |

槽内通道强制：`DWORD` 低位对应通道 1。

## AQ 公式

全局通道号 `n`（从 1 起）：`mA = 4 + ((n-1) MOD 8)`，即 **4～11 mA 循环**。  
**4～20 mA 组态**：`Raw = (mA − EngMin) / (EngMax − EngMin) × RawFull`  
（4 mA→0，20 mA→27648）。

## AI 换算

`mA = EngMin + raw/RawFull × (EngMax − EngMin)`；播报毫安取整（4.2→「四毫安」）。
