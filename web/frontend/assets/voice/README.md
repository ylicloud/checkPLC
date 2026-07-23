# 语音词片目录

体积很小（约十几 KB），**允许提交到 git**。换机一般无需再生成。

| 文件 | 内容 |
|------|------|
| `1.mp3` … `32.mp3` | 整段通道号 |
| `ma0.mp3` … `ma24.mp3` | 整段「N毫安」（数字与毫安一次合成，无停顿） |
| `ma_over24.mp3` | 「超出二十四毫安」 |

重新生成：

```bash
pip install edge-tts
python scripts/generate_wavs.py
```
