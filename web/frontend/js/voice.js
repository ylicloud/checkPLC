/**
 * Prefers preloaded WAV/MP3 clips (low latency). Falls back to speechSynthesis.
 * Files under /assets/voice/: tongdao, haoan, dian, shi, 0..10
 */
const Voice = (() => {
  const base = "/assets/voice/";
  const cache = new Map();
  let ready = false;
  let queue = Promise.resolve();
  let voicesReady = false;
  let lastKey = "";
  let lastAt = 0;

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

  function playBuffer(buf) {
    return new Promise(async (resolve) => {
      try {
        const ctx = audioCtx();
        if (ctx.state === "suspended") await ctx.resume();
        const src = ctx.createBufferSource();
        src.buffer = buf;
        src.connect(ctx.destination);
        src.onended = () => resolve();
        src.start();
      } catch {
        resolve();
      }
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
      warmUpTts();
      // Chrome：cancel 后立刻 speak 常会静默失败，稍延后
      speechSynthesis.cancel();
      setTimeout(() => {
        try {
          const u = new SpeechSynthesisUtterance(String(text || ""));
          u.lang = "zh-CN";
          u.rate = 1.0;
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
          // 防止个别浏览器既不触发 end 也不触发 error
          setTimeout(finish, 4000);
          speechSynthesis.speak(u);
        } catch {
          resolve();
        }
      }, 60);
    });
  }

  function enqueue(task) {
    queue = queue.then(task).catch(() => {});
    return queue;
  }

  function phraseFor(ev) {
    if (ev.kind === "ai") {
      // 不说「通道」，只报数字 + 毫安，更快
      const ma = Math.max(0, Math.round(ev.ma ?? 0));
      return `${zhNumber(ev.channel)}，${zhNumber(ma)}毫安`;
    }
    // DI / DQ：只报数字，如「一」「十二」
    return zhNumber(ev.channel);
  }

  return {
    preload,
    unlock,
    reset() {
      try {
        if (window.speechSynthesis) speechSynthesis.cancel();
      } catch {
        /* ignore */
      }
      queue = Promise.resolve();
      lastKey = "";
      lastAt = 0;
    },
    announce(ev) {
      // 同步去重：避免「按钮播报 + 异步队列」在 TTS 播完后又播第二遍
      const key = `${ev.kind}:${ev.channel}:${Math.round(ev.ma ?? 0)}`;
      const now = Date.now();
      if (key === lastKey && now - lastAt < 1200) return queue;
      lastKey = key;
      lastAt = now;
      return enqueue(async () => {
        await unlock();
        let ok = false;
        if (ready) {
          if (ev.kind === "di" || ev.kind === "dq") ok = await speakWavNumber(ev.channel);
          else if (ev.kind === "ai") ok = await speakWavAi(ev.channel, ev.ma ?? 0);
        }
        if (!ok) await speakTts(phraseFor(ev));
      });
    },
    sayChannel(channel) {
      return this.announce({ kind: "dq", channel, text: zhNumber(channel) });
    },
  };
})();
