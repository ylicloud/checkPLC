# 语音词片目录

**格式：只用 `.mp3`，不用 `.wav`。**  
`scripts/generate_wavs.py` 名字里虽有 wav，实际输出的是 mp3。前端也只请求 `/assets/voice/*.mp3`。

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

若后台仍出现 `GET /assets/voice/xxx.wav 404`，说明浏览器还在用旧版 `voice.js`，请 **Ctrl+F5** 强制刷新。
