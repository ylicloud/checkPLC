# 语音词片目录

每个通道号 **一个整段 mp3**，前端直接播放（不运行时拼字）。

| 文件 | 听感 |
|------|------|
| `30.mp3` | 「三十」（整段合成） |
| `32.mp3` | 「三二」（整段合成，与三十同速连续） |
| `ma4.mp3`… | 「N毫安」 |

```bash
pip install edge-tts
python scripts/generate_wavs.py
```
