/**
 * 预加载整段 WAV/MP3：1 个通道号 = 1 个文件，直接播放，不动态拼文字。
 * 词片：/assets/voice/1..32、ma4..ma20（由 scripts/generate_wavs.py 离线生成）
 */
const Voice = (() => {
  const base = "/assets/voice/";
  const cache = new Map();
  let ready = false;
  let lastKey = "";
  let lastAt = 0;
  let rate = 1.0;
  let playGen = 0;
  /** @type {AudioBufferSourceNode[]} */
  let currentSources = [];

  function preloadKeys() {
    const keys = [];
    for (let i = 1; i <= 32; i++) keys.push(String(i));
    for (let i = 4; i <= 20; i++) keys.push(`ma${i}`);
    return keys;
  }

  async function loadOne(k) {
    for (const ext of ["wav", "mp3"]) {
      const url = `${base}${k}.${ext}`;
      try {
        const res = await fetch(url, { cache: "force-cache" });
        if (!res.ok) continue;
        const buf = await res.arrayBuffer();
        const ctx = audioCtx();
        const decoded = await ctx.decodeAudioData(buf.slice(0));
        cache.set(k, decoded);
        return true;
      } catch {
        /* try next ext */
      }
    }
    return false;
  }

  async function preload() {
    const keys = preloadKeys();
    const batch = 8;
    for (let i = 0; i < keys.length; i += batch) {
      await Promise.all(keys.slice(i, i + batch).map(loadOne));
    }
    ready = cache.size > 0;
    return ready;
  }

  let _ctx;
  function audioCtx() {
    if (!_ctx) _ctx = new (window.AudioContext || window.webkitAudioContext)();
    return _ctx;
  }

  async function unlock() {
    try {
      const ctx = audioCtx();
      if (ctx.state === "suspended") await ctx.resume();
    } catch {
      /* ignore */
    }
  }

  function stopSpeaking() {
    playGen += 1;
    try {
      if (window.speechSynthesis) speechSynthesis.cancel();
    } catch {
      /* ignore */
    }
    for (const src of currentSources) {
      try {
        src.onended = null;
        src.stop();
      } catch {
        /* ignore */
      }
    }
    currentSources = [];
    return playGen;
  }

  function playBuffer(buf, gen) {
    return new Promise(async (resolve) => {
      if (gen !== playGen) {
        resolve();
        return;
      }
      try {
        const ctx = audioCtx();
        if (ctx.state === "suspended") await ctx.resume();
        if (gen !== playGen) {
          resolve();
          return;
        }
        const src = ctx.createBufferSource();
        src.buffer = buf;
        src.playbackRate.value = rate;
        src.connect(ctx.destination);
        currentSources.push(src);
        src.onended = () => {
          currentSources = currentSources.filter((x) => x !== src);
          resolve();
        };
        src.start();
      } catch {
        resolve();
      }
    });
  }

  /** 只播整段文件，不拼接、不拼文字 */
  async function speakWhole(key, gen) {
    const buf = cache.get(String(key));
    if (!buf) return false;
    await playBuffer(buf, gen);
    return true;
  }

  async function speakWavNumber(channel, gen) {
    return speakWhole(channel, gen);
  }

  async function speakWavAi(channel, ma, gen) {
    const n = Math.max(0, Math.round(ma));
    const okCh = await speakWhole(channel, gen);
    if (!okCh || gen !== playGen) return okCh;
    // 毫安也用整段 maN；没有则只报通道号
    if (cache.has(`ma${n}`)) {
      await speakWhole(`ma${n}`, gen);
    }
    return true;
  }

  function normalizeRate(r) {
    const v = Number(r);
    const allowed = [1, 1.2, 1.5, 1.8, 2];
    return allowed.includes(v) ? v : 1;
  }

  return {
    preload,
    unlock,
    setRate(r) {
      rate = normalizeRate(r);
      try {
        localStorage.setItem("checkplc_voice_rate", String(rate));
      } catch {
        /* ignore */
      }
      return rate;
    },
    getRate() {
      return rate;
    },
    reset() {
      stopSpeaking();
      lastKey = "";
      lastAt = 0;
    },
    announce(ev) {
      const key = `${ev.kind}:${ev.channel}:${Math.round(ev.ma ?? 0)}`;
      const now = Date.now();
      if (key === lastKey && now - lastAt < 400) return;
      lastKey = key;
      lastAt = now;

      const gen = stopSpeaking();
      (async () => {
        await unlock();
        if (gen !== playGen) return;
        if (!ready) {
          console.warn("[Voice] 词片未加载，请运行: python scripts/generate_wavs.py");
          return;
        }
        if (ev.kind === "di" || ev.kind === "dq") {
          const ok = await speakWavNumber(ev.channel, gen);
          if (!ok) console.warn("[Voice] 缺少整段词片:", ev.channel);
        } else if (ev.kind === "ai") {
          const ok = await speakWavAi(ev.channel, ev.ma ?? 0, gen);
          if (!ok) console.warn("[Voice] 缺少整段词片:", ev.channel);
        }
      })().catch(() => {});
    },
    sayChannel(channel) {
      this.announce({ kind: "dq", channel });
    },
  };
})();
