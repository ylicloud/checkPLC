/**
 * Prefers preloaded WAV/MP3 clips (low latency). Falls back to speechSynthesis.
 * Files under /assets/voice/: 1..32 整段数字、ma4..ma20、haoan、0..10、shi …
 * 新播报立即打断旧播报；支持 1× / 1.5× / 2× 语速；>20 简化读音（21→二一）。
 */
const Voice = (() => {
  const base = "/assets/voice/";
  const cache = new Map();
  let ready = false;
  let voicesReady = false;
  let lastKey = "";
  let lastAt = 0;
  let rate = 1.0;
  let playGen = 0;
  /** @type {AudioBufferSourceNode[]} */
  let currentSources = [];

  function preloadKeys() {
    const keys = ["tongdao", "haoan", "dian", "shi"];
    for (let i = 0; i <= 32; i++) keys.push(String(i));
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
    // 分批并发，避免一次打爆连接
    const keys = preloadKeys();
    const batch = 8;
    for (let i = 0; i < keys.length; i += batch) {
      await Promise.all(keys.slice(i, i + batch).map(loadOne));
    }
    ready = cache.size > 0;
    warmUpTts();
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
    warmUpTts();
  }

  function warmUpTts() {
    if (!window.speechSynthesis) return;
    const load = () => {
      const list = speechSynthesis.getVoices();
      if (list && list.length) voicesReady = true;
    };
    load();
    if (typeof speechSynthesis.onvoiceschanged !== "undefined") {
      speechSynthesis.onvoiceschanged = load;
    }
  }

  function pickZhVoice() {
    const list = speechSynthesis.getVoices() || [];
    return (
      list.find((v) => /zh[-_]?CN/i.test(v.lang) && /Xiaoxiao|Xiaoyi|Huihui|Yaoyao|Kangkang/i.test(v.name)) ||
      list.find((v) => /zh[-_]?CN/i.test(v.lang)) ||
      list.find((v) => /^zh/i.test(v.lang)) ||
      null
    );
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

  function numberClips(n) {
    const clips = [];
    n = Math.floor(Number(n) || 0);
    if (n < 0) n = 0;
    // 优先整段 0..32（一次播放，无拼接间隙）
    if (cache.has(String(n))) {
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
      if (ones === 0) {
        if (cache.has("shi")) clips.push(cache.get("shi"));
      } else if (cache.has(String(ones))) {
        clips.push(cache.get(String(ones)));
      }
      return clips;
    }
    return [];
  }

  async function speakWavNumber(channel, gen) {
    const parts = numberClips(channel);
    if (!parts.length) return false;
    for (const p of parts) {
      if (gen !== playGen) return true;
      await playBuffer(p, gen);
    }
    return true;
  }

  async function speakWavAi(channel, ma, gen) {
    const parts = [...numberClips(channel)];
    const n = Math.max(0, Math.round(ma));
    // 优先整段「四毫安」类词片
    if (cache.has(`ma${n}`)) {
      parts.push(cache.get(`ma${n}`));
    } else {
      parts.push(...numberClips(n));
      if (cache.has("haoan")) parts.push(cache.get("haoan"));
    }
    if (!parts.length) return false;
    for (const p of parts) {
      if (gen !== playGen) return true;
      await playBuffer(p, gen);
    }
    return true;
  }

  function zhNumber(n) {
    const digits = "零一二三四五六七八九";
    n = Math.floor(Number(n) || 0);
    if (n < 0) n = 0;
    if (n <= 10) return ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"][n];
    if (n < 20) return "十" + (n > 10 ? digits[n - 10] : "");
    if (n < 100) {
      const tens = Math.floor(n / 10);
      const ones = n % 10;
      if (ones === 0) return digits[tens] + "十";
      // >20：不读「十」→ 二一
      return digits[tens] + digits[ones];
    }
    return String(n);
  }

  function speakTts(text, gen) {
    return new Promise((resolve) => {
      if (!window.speechSynthesis || gen !== playGen) {
        resolve();
        return;
      }
      warmUpTts();
      // Chrome：cancel 后立刻 speak 常会静默失败，稍延后
      speechSynthesis.cancel();
      setTimeout(() => {
        if (gen !== playGen) {
          resolve();
          return;
        }
        try {
          const u = new SpeechSynthesisUtterance(String(text || ""));
          u.lang = "zh-CN";
          u.rate = rate;
          u.pitch = 1.0;
          const voice = pickZhVoice();
          if (voice) u.voice = voice;
          let done = false;
          const finish = () => {
            if (done) return;
            done = true;
            resolve();
          };
          u.onend = finish;
          u.onerror = finish;
          const maxMs = Math.max(1500, Math.round(4000 / rate));
          setTimeout(finish, maxMs);
          speechSynthesis.speak(u);
        } catch {
          resolve();
        }
      }, 40);
    });
  }

  function phraseFor(ev) {
    if (ev.kind === "ai") {
      const ma = Math.max(0, Math.round(ev.ma ?? 0));
      return `${zhNumber(ev.channel)}，${zhNumber(ma)}毫安`;
    }
    return zhNumber(ev.channel);
  }

  function normalizeRate(r) {
    const v = Number(r);
    if (v === 1.5 || v === 2 || v === 2.0) return v === 2.0 ? 2 : v;
    return 1;
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
      // 相同内容极短去重；不同内容立即打断旧播报
      const key = `${ev.kind}:${ev.channel}:${Math.round(ev.ma ?? 0)}`;
      const now = Date.now();
      if (key === lastKey && now - lastAt < 400) return;
      lastKey = key;
      lastAt = now;

      const gen = stopSpeaking();
      (async () => {
        await unlock();
        if (gen !== playGen) return;
        let ok = false;
        if (ready) {
          if (ev.kind === "di" || ev.kind === "dq") ok = await speakWavNumber(ev.channel, gen);
          else if (ev.kind === "ai") ok = await speakWavAi(ev.channel, ev.ma ?? 0, gen);
        }
        if (gen !== playGen) return;
        if (!ok) await speakTts(phraseFor(ev), gen);
      })().catch(() => {});
    },
    sayChannel(channel) {
      this.announce({ kind: "dq", channel, text: zhNumber(channel) });
    },
  };
})();
