/**
 * Prefers preloaded WAV clips (low latency). Falls back to speechSynthesis.
 * Expected files under /assets/voice/: tongdao.wav, hao.wav (optional),
 * 0..10, shi, bai, dian, haoan (毫安), and optionally full phrases.
 */
const Voice = (() => {
  const base = "/assets/voice/";
  const cache = new Map();
  let ready = false;
  let queue = Promise.resolve();

  const NAMES = {
    tongdao: "tongdao",
    ma: "haoan",
    dian: "dian",
    shi: "shi",
    ...Object.fromEntries([...Array(11)].map((_, i) => [String(i), String(i)])),
  };

  async function preload() {
    const keys = ["tongdao", "haoan", "dian", "shi", ...Array.from({ length: 11 }, (_, i) => String(i))];
    await Promise.all(
      keys.map(async (k) => {
        for (const ext of ["wav", "mp3"]) {
          const url = `${base}${k}.${ext}`;
          try {
            const res = await fetch(url, { cache: "force-cache" });
            if (!res.ok) continue;
            const buf = await res.arrayBuffer();
            const ctx = audioCtx();
            const decoded = await ctx.decodeAudioData(buf.slice(0));
            cache.set(k, decoded);
            break;
          } catch {
            /* try next ext */
          }
        }
      })
    );
    ready = cache.size > 0;
    return ready;
  }

  let _ctx;
  function audioCtx() {
    if (!_ctx) _ctx = new (window.AudioContext || window.webkitAudioContext)();
    return _ctx;
  }

  function playBuffer(buf) {
    return new Promise((resolve) => {
      const ctx = audioCtx();
      if (ctx.state === "suspended") ctx.resume();
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(ctx.destination);
      src.onended = () => resolve();
      src.start();
    });
  }

  function numberClips(n) {
    const clips = [];
    if (n <= 10 && cache.has(String(n))) {
      clips.push(cache.get(String(n)));
      return clips;
    }
    if (n < 20) {
      if (cache.has("shi")) clips.push(cache.get("shi"));
      const ones = n - 10;
      if (ones > 0 && cache.has(String(ones))) clips.push(cache.get(String(ones)));
      return clips;
    }
    if (n < 100) {
      const tens = Math.floor(n / 10);
      const ones = n % 10;
      if (cache.has(String(tens))) clips.push(cache.get(String(tens)));
      if (cache.has("shi")) clips.push(cache.get("shi"));
      if (ones && cache.has(String(ones))) clips.push(cache.get(String(ones)));
      return clips;
    }
    return [];
  }

  async function speakWavNumber(channel) {
    const parts = numberClips(channel);
    if (!parts.length) return false;
    for (const p of parts) await playBuffer(p);
    return true;
  }

  async function speakWavAi(channel, ma) {
    // 只播整数毫安，如 4.2 →「四」「毫安」；通道号仍先播
    const parts = [...numberClips(channel)];
    const n = Math.max(0, Math.round(ma));
    parts.push(...numberClips(n));
    if (cache.has("haoan")) parts.push(cache.get("haoan"));
    if (!parts.length) return false;
    for (const p of parts) await playBuffer(p);
    return true;
  }

  function zhNumber(n) {
    const digits = "零一二三四五六七八九";
    if (n <= 10) return ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"][n];
    if (n < 20) return "十" + (n > 10 ? digits[n - 10] : "");
    if (n < 100) {
      const tens = Math.floor(n / 10);
      const ones = n % 10;
      return digits[tens] + "十" + (ones ? digits[ones] : "");
    }
    return String(n);
  }

  function speakTts(text) {
    return new Promise((resolve) => {
      if (!window.speechSynthesis) {
        resolve();
        return;
      }
      const u = new SpeechSynthesisUtterance(text);
      u.lang = "zh-CN";
      u.rate = 1.05;
      u.onend = () => resolve();
      u.onerror = () => resolve();
      speechSynthesis.cancel();
      speechSynthesis.speak(u);
    });
  }

  function enqueue(task) {
    queue = queue.then(task).catch(() => {});
    return queue;
  }

  return {
    preload,
    announce(ev) {
      return enqueue(async () => {
        let ok = false;
        if (ready) {
          if (ev.kind === "di" || ev.kind === "dq") ok = await speakWavNumber(ev.channel);
          else if (ev.kind === "ai") ok = await speakWavAi(ev.channel, ev.ma ?? 0);
        }
        const text = ev.text || (ev.kind === "ai" ? `${zhNumber(ev.channel)}` : zhNumber(ev.channel));
        if (!ok) await speakTts(text);
      });
    },
    sayChannel(channel) {
      return this.announce({ kind: "dq", channel, text: zhNumber(channel) });
    },
  };
})();
