# 语音词片目录

放置预录词片（优先 `.wav`，也支持 `.mp3`）：

| 文件名 | 内容 |
|--------|------|
| tongdao | 通道 |
| 0..10 | 零…十 |
| shi | 十 |
| dian | 点 |
| haoan | 毫安 |

生成：

```bash
pip install edge-tts
python scripts/generate_wavs.py
```

若尚无词片，页面会自动回退到浏览器中文 TTS（延迟略高）。
