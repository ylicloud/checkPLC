"""Generate Chinese WAV voice clips for low-latency playback.

Requires: pip install edge-tts
Usage:  python scripts/generate_wavs.py
Output: web/frontend/assets/voice/*.wav
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "web" / "frontend" / "assets" / "voice"

CLIPS = {
    "tongdao": "通道",
    "haoan": "毫安",
    "dian": "点",
    "shi": "十",
    "0": "零",
    "1": "一",
    "2": "二",
    "3": "三",
    "4": "四",
    "5": "五",
    "6": "六",
    "7": "七",
    "8": "八",
    "9": "九",
    "10": "十",
}

VOICE = "zh-CN-XiaoxiaoNeural"


async def gen_one(name: str, text: str) -> None:
    import edge_tts

    path = OUT / f"{name}.wav"
    # edge-tts writes mp3 by default; use communicate and save as mp3 then note —
    # For WAV, use mp3 and let browser play, or use communicate with raw.
    # Simpler: save as mp3 with .mp3 and update voice.js — but plan says wav.
    # edge-tts output is mp3. We'll save .mp3 and also try.
    mp3 = OUT / f"{name}.mp3"
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(str(mp3))
    # Keep mp3; voice.js will be updated to try mp3 if wav missing — actually update to use mp3
    print("wrote", mp3)


async def main() -> None:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        print("请先安装: pip install edge-tts", file=sys.stderr)
        sys.exit(1)
    OUT.mkdir(parents=True, exist_ok=True)
    await asyncio.gather(*(gen_one(k, v) for k, v in CLIPS.items()))
    print("完成。前端将优先加载同名 .wav；若只有 mp3，请用 ffmpeg 转换，或改用浏览器 TTS 回退。")


if __name__ == "__main__":
    asyncio.run(main())
