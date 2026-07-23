"""Generate whole-number voice clips (1 file = 1 announce).

Requires: pip install edge-tts
Usage:  python scripts/generate_wavs.py
Output: web/frontend/assets/voice/*.mp3

- 通道号 1~32：整段合成
- 毫安 ma0~ma24：整段「四毫安」（数字+毫安一次合成，无停顿）
- ma_over24：「超出二十四毫安」
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "web" / "frontend" / "assets" / "voice"

VOICE = "zh-CN-XiaoxiaoNeural"
RATE = "+25%"

CAPS = "零壹贰叁肆伍陆柒捌玖"
DIGITS = "零一二三四五六七八九"


def speak_text(n: int) -> str:
    """通道号 / 数值读音（>20 简化，用大写避免念成「三十二」）。"""
    if n < 0:
        n = 0
    if n <= 10:
        return ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"][n]
    if n < 20:
        return "十" + DIGITS[n - 10]
    if n < 100:
        tens, ones = divmod(n, 10)
        if ones == 0:
            return DIGITS[tens] + "十"
        return CAPS[tens] + CAPS[ones]
    return str(n)


def ma_speak_text(n: int) -> str:
    """毫安整段：一次合成「四毫安」，避免「四」+「毫安」拼接停顿。"""
    return speak_text(n) + "毫安"


async def gen_one(name: str, text: str, sem: asyncio.Semaphore) -> None:
    import edge_tts

    path = OUT / f"{name}.mp3"
    async with sem:
        await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(path))
        print("wrote", path.name, "←", text)


async def main() -> None:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        print("请先安装: pip install edge-tts", file=sys.stderr)
        sys.exit(1)

    OUT.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(4)

    extras = {
        "haoan": "毫安",
        "shi": "十",
        "dian": "点",
        "tongdao": "通道",
        "0": "零",
        "ma_over24": "超出二十四毫安",
    }
    tasks = [gen_one(str(n), speak_text(n), sem) for n in range(1, 33)]
    tasks += [gen_one(k, v, sem) for k, v in extras.items()]
    # ma0~ma24：整段「N毫安」
    tasks += [gen_one(f"ma{n}", ma_speak_text(n), sem) for n in range(0, 25)]
    await asyncio.gather(*tasks)

    print(f"完成 → {OUT}")
    print("通道 1..32；毫安 ma0..ma24（整段）；超出 → ma_over24")


if __name__ == "__main__":
    asyncio.run(main())
