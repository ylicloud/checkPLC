/**
 * 整段 MP3 播报：1 个通道号 = 1 个文件。
 * 使用 HTMLAudioElement（与资源管理器/浏览器直接打开 mp3 同一路径），
 * 避免 AudioContext 在 setInterval 轮询触发时仍 suspended 导致无声。
 * 词片：/assets/voice/1..32、ma0..ma24、ma_over24（scripts/generate_wavs.py）
 */
const Voice = (() => {
  const base = "/assets/voice/";
  /** @type {Set<string>} */
  const available = new Set();
  let ready = false;
  let lastKey = "";
  let lastAt = 0;
  let rate = 1.0;
  let playGen = 0;
  /** @type {HTMLAudioElement | null} */
  let current = null;
  let unlocked = false;

  function preloadKeys() {
    const keys = ["ma_over24"];
    for (let i = 1; i <= 32; i++) keys.push(String(i));
    for (let i = 0; i <= 24; i++) keys.push(`ma${i}`);
    return keys;
  }

  async function loadOne(k) {
    for (const ext of ["wav", "mp3"]) {
      const url = `${base}${k}.${ext}`;
      try {
        const res = await fetch(url, { cache: "no-cache" });
        if (!res.ok) continue;
        // 只需确认存在；丢弃 body，真正播放走 <audio src>
        await res.arrayBuffer();
        available.add(String(k));
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
    ready = available.size > 0;
    if (!ready) {
      console.warn("[Voice] 词片未加载，请运行: python scripts/generate_wavs.py ，然后强制刷新页面");
    } else {
      console.info("[Voice] 已加载词片", available.size, "/", keys.length);
    }
    return ready;
  }

  function clipUrl(key) {
    return `${base}${key}.mp3`;
  }

  async function unlock() {
    unlocked = true;
    // 部分浏览器需在用户手势内 play 一次；播极短静音唤醒策略
    try {
      if (!current) {
        const a = new Audio("data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA=");
        a.volume = 0.01;
        await a.play().catch(() => {});
        a.pause();
      }
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
    if (current) {
      try {
        current.onended = null;
        current.onerror = null;
        current.pause();
        current.removeAttribute("src");
        current.load();
      } catch {
        /* ignore */
      }
      current = null;
    }
    return playGen;
  }

  function playUrl(url, gen) {
    return new Promise((resolve) => {
      if (gen !== playGen) {
        resolve(false);
        return;
      }
      const audio = new Audio(url);
      audio.playbackRate = rate;
      audio.preload = "auto";
      current = audio;
      const done = (ok) => {
        if (current === audio) current = null;
        resolve(ok);
      };
      audio.onended = () => done(true);
      audio.onerror = () => {
        console.warn("[Voice] 播放失败:", url);
        done(false);
      };
      const p = audio.play();
      if (p && typeof p.then === "function") {
        p.catch((err) => {
          console.warn("[Voice] play() 被拒绝（需先点击页面）:", err && err.message ? err.message : err);
          done(false);
        });
      }
    });
  }

  async function speakWhole(key, gen) {
    const k = String(key);
    if (ready && !available.has(k)) return false;
    return playUrl(clipUrl(k), gen);
  }

  async function speakWavNumber(channel, gen) {
    return speakWhole(channel, gen);
  }

  async function speakWavAi(channel, ma, gen) {
    const okCh = await speakWhole(channel, gen);
    if (!okCh || gen !== playGen) return okCh;
    const n = Math.round(Number(ma) || 0);
    if (n > 24) {
      await speakWhole("ma_over24", gen);
    } else {
      const key = `ma${Math.max(0, n)}`;
      if (!ready || available.has(key)) {
        await speakWhole(key, gen);
      }
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
      if (current) {
        try {
          current.playbackRate = rate;
        } catch {
          /* ignore */
        }
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
        if (!unlocked) await unlock();
        if (gen !== playGen) return;
        if (!ready) {
          console.warn("[Voice] 词片未加载，请运行: python scripts/generate_wavs.py");
          return;
        }
        if (ev.kind === "di" || ev.kind === "dq") {
          const ok = await speakWavNumber(ev.channel, gen);
          if (!ok) console.warn("[Voice] 缺少或无法播放词片:", ev.channel);
        } else if (ev.kind === "ai") {
          const ok = await speakWavAi(ev.channel, ev.ma ?? 0, gen);
          if (!ok) console.warn("[Voice] 缺少或无法播放词片:", ev.channel);
        }
      })().catch((e) => console.warn("[Voice] announce 异常", e));
    },
    sayChannel(channel) {
      this.announce({ kind: "dq", channel });
    },
  };
})();
