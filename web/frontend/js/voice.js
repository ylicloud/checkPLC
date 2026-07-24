/**
 * 整段语音：统一只用 .mp3（scripts/generate_wavs.py 也只生成 mp3）。
 * 路径：/assets/voice/1..32、ma0..ma24、ma_over24
 *
 * 禁止再请求 .wav（旧版会先试 wav 导致后台刷 404）。
 */
const Voice = (() => {
  const base = "/assets/voice/";
  /** @type {Map<string, string>} key -> blob: URL（加速；缺失时回退网络 mp3） */
  const blobUrls = new Map();
  let ready = false;
  let lastKey = "";
  let lastAt = 0;
  let rate = 1.0;
  let playGen = 0;
  /** @type {HTMLAudioElement | null} */
  let current = null;
  let unlocked = false;

  const SILENT_WAV =
    "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA=";

  function preloadKeys() {
    const keys = ["ma_over24"];
    for (let i = 1; i <= 32; i++) keys.push(String(i));
    for (let i = 0; i <= 24; i++) keys.push(`ma${i}`);
    return keys;
  }

  async function loadOne(k) {
    const url = `${base}${k}.mp3`;
    try {
      const res = await fetch(url, { cache: "force-cache" });
      if (!res.ok) return false;
      const ab = await res.arrayBuffer();
      if (!ab || ab.byteLength < 32) return false;
      const obj = URL.createObjectURL(new Blob([ab], { type: "audio/mpeg" }));
      const prev = blobUrls.get(String(k));
      if (prev) {
        try {
          URL.revokeObjectURL(prev);
        } catch {
          /* ignore */
        }
      }
      blobUrls.set(String(k), obj);
      return true;
    } catch {
      return false;
    }
  }

  async function preload() {
    const keys = preloadKeys();
    const batch = 8;
    for (let i = 0; i < keys.length; i += batch) {
      await Promise.all(keys.slice(i, i + batch).map(loadOne));
    }
    ready = true; // 即使部分失败，也允许按 URL 直接播 mp3
    const miss = keys.filter((k) => !blobUrls.has(k));
    console.info(
      "[Voice] 词片预载",
      blobUrls.size,
      "/",
      keys.length,
      miss.length ? `未入缓存(将直链mp3): ${miss.slice(0, 12).join(",")}${miss.length > 12 ? "…" : ""}` : ""
    );
    return blobUrls.size > 0;
  }

  function clipUrl(key) {
    const k = String(key);
    return blobUrls.get(k) || `${base}${k}.mp3`;
  }

  /** 仅用静音 dataURI 解锁，避免占用 1.mp3 与通道播报打架 */
  function unlock() {
    if (unlocked) return Promise.resolve();
    unlocked = true;
    try {
      const a = new Audio(SILENT_WAV);
      a.volume = 0.01;
      const p = a.play();
      if (p && typeof p.then === "function") {
        return p
          .then(() => {
            try {
              a.pause();
            } catch {
              /* ignore */
            }
          })
          .catch(() => {});
      }
    } catch {
      /* ignore */
    }
    return Promise.resolve();
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
      const audio = new Audio();
      audio.preload = "auto";
      audio.playbackRate = rate;
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
      audio.src = url;
      const p = audio.play();
      if (p && typeof p.then === "function") {
        p.catch((err) => {
          console.warn(
            "[Voice] play() 被拒绝（请先点击页面）:",
            err && err.message ? err.message : err
          );
          done(false);
        });
      }
    });
  }

  function speakWhole(key, gen) {
    return playUrl(clipUrl(key), gen);
  }

  function speakNumber(channel, gen) {
    return speakWhole(String(channel), gen);
  }

  async function speakAi(channel, ma, gen) {
    const okCh = await speakWhole(String(channel), gen);
    if (!okCh || gen !== playGen) return okCh;
    const n = Math.round(Number(ma) || 0);
    if (n > 24) return speakWhole("ma_over24", gen);
    return speakWhole(`ma${Math.max(0, n)}`, gen);
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
      if (!unlocked) unlock();
      (async () => {
        if (gen !== playGen) return;
        if (ev.kind === "di" || ev.kind === "dq") {
          const ok = await speakNumber(ev.channel, gen);
          if (!ok) console.warn("[Voice] 无法播放通道:", ev.channel);
        } else if (ev.kind === "ai") {
          const ok = await speakAi(ev.channel, ev.ma ?? 0, gen);
          if (!ok) console.warn("[Voice] 无法播放 AI:", ev.channel);
        }
      })().catch((e) => console.warn("[Voice] announce 异常", e));
    },
    sayChannel(channel) {
      this.announce({ kind: "dq", channel: Number(channel) });
    },
  };
})();
