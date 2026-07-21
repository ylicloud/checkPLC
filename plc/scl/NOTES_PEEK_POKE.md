# 补充说明：PEEK/POKE

`FC_IO_Apply.scl` 使用 `PEEK` / `POKE` / `POKE_W` 写过程映像。

若你的 TIA/CPU 固件不支持或编译报错，可选：

1. 在设备组态里为通检专用建立「已知地址」的直接赋值（按柜改 FC），或  
2. 使用西门子间接寻址库 / `WRIT_DBL` 等等价指令改写本 FC。

Web 侧对 DI/AI 的读取不依赖 PEEK，只要过程映像可读即可。
