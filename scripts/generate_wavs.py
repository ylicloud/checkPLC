"""Generate whole-number voice clips (1 file = 1 announce).

Requires: pip install edge-tts
Usage:  python scripts/generate_wavs.py
Output: web/frontend/assets/voice/*.mp3

每个通道号一个整段 mp3，前端直接播放。
>20 的简化读音（三二）用「大写数字」整段合成（叁贰），
避免引擎念成「三十二」，也避免「三」+「二」两段拼接变慢。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "web" / "frontend" / "assets" / "voice"

VOICE = "zh-CN-XiaoxiaoNeural"
RATE = "+25%"

# 大写数字：TTS 通常按字读，不会把「叁贰」展开成「三十二」
CAPS = "零壹贰叁肆伍陆柒捌玖"
DIGITS = "零一二三四五六七八九"


def speak_text(n: int) -> str:
    """整段合成用的文本（听感连续、速度接近「三十」）。"""
    if n <= 10:
        return ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"][n]
    if n < 20:
        return "十" + DIGITS[n - 10]
    if n < 100:
        tens, ones = divmod(n, 10)
        if ones == 0:
            return DIGITS[tens] + "十"  # 二十、三十
        # 简化两位：用大写整段「叁贰」，一次合成、不停顿
        return CAPS[tens] + CAPS[ones]
    return str(n)


def concat_mp3(parts: list[Path], dest: Path) -> None:
    dest.write_bytes(b"".join(p.read_bytes() for p in parts))


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
    }
    # 1~32：全部整段一次合成（含简化的 21~32）
    tasks = [gen_one(str(n), speak_text(n), sem) for n in range(1, 33)]
    tasks += [gen_one(k, v, sem) for k, v in extras.items()]
    await asyncio.gather(*tasks)

    # ma4~ma20 = 数字整段 + 毫安（仅此处离线拼接文件，前端仍播一个 maN）
    haoan = OUT / "haoan.mp3"
    for n in range(4, 21):
        concat_mp3([OUT / f"{n}.mp3", haoan], OUT / f"ma{n}.mp3")
        print("wrote", f"ma{n}.mp3", "←", f"{n}+haoan")

    print(f"完成 → {OUT}")
    print("示例: 30←三十, 32←叁贰(读作三二, 单段连续)")


if __name__ == "__main__":
    asyncio.run(main())
