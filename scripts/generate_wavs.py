"""Generate Chinese voice clips for low-latency playback.

Requires: pip install edge-tts
Usage:  python scripts/generate_wavs.py
Output: web/frontend/assets/voice/*.mp3

优先生成 1~32 整段数字（与播报简化读音一致，如 21→二一），
前端直接播一整段，比「十+一」拼接或浏览器 TTS 更快。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "web" / "frontend" / "assets" / "voice"

VOICE = "zh-CN-XiaoxiaoNeural"
# 略提速：edge-tts rate；前端还可再设 playbackRate
RATE = "+20%"


def zh_number(n: int) -> str:
    """与 scanner / voice.js 一致：>20 不读「十」（21→二一）。"""
    digits = "零一二三四五六七八九"
    if n <= 10:
        return ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"][n]
    if n < 20:
        return "十" + (digits[n - 10] if n > 10 else "")
    if n < 100:
        tens, ones = divmod(n, 10)
        if ones == 0:
            return digits[tens] + "十"
        return digits[tens] + digits[ones]
    return str(n)


def build_clips() -> dict[str, str]:
    clips: dict[str, str] = {
        "tongdao": "通道",
        "haoan": "毫安",
        "dian": "点",
        "shi": "十",
    }
    # 个位词片（AI 毫安拼接兜底）
    for i in range(0, 11):
        clips[str(i)] = zh_number(i)
    # 1~32 整段：通道号直播
    for i in range(1, 33):
        clips[str(i)] = zh_number(i)
    # 常用毫安整段（4~20），AI 可「通道+毫安」两段拼完
    for i in range(4, 21):
        clips[f"ma{i}"] = f"{zh_number(i)}毫安"
    return clips


async def gen_one(name: str, text: str, sem: asyncio.Semaphore) -> None:
    import edge_tts

    async with sem:
        mp3 = OUT / f"{name}.mp3"
        communicate = edge_tts.Communicate(text, VOICE, rate=RATE)
        await communicate.save(str(mp3))
        print("wrote", mp3.name, "←", text)


async def main() -> None:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        print("请先安装: pip install edge-tts", file=sys.stderr)
        sys.exit(1)
    OUT.mkdir(parents=True, exist_ok=True)
    clips = build_clips()
    # 限流，避免 edge 并发过多失败
    sem = asyncio.Semaphore(4)
    await asyncio.gather(*(gen_one(k, v, sem) for k, v in clips.items()))
    print(f"完成，共 {len(clips)} 个词片 → {OUT}")
    print("前端优先加载整段 1..32.mp3；缺失时回退拼接或 TTS。")


if __name__ == "__main__":
    asyncio.run(main())
