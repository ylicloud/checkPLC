let cabinet = null;
let currentKind = "di";
let pollTimer = null;
let lastDqForce = null;
let lastDqQMasks = null;
let dqBuiltKey = "";
let lastDiStates = {};
let lastAiValues = {};
let lastAqValues = [];
/** 连接状态以本地为准，避免 poll 瞬时失败把右上角打回「未连接」 */
let plcConnected = false;
let plcMock = false;
/** DQ 乐观更新保护；复位时允许同步全 0 */
let dqHoldUntil = 0;
let dqAllowZeroFromServer = false;

const $ = (id) => document.getElementById(id);

/** 数字量：起始字节 + 通道(0-based) → I0.0 / Q0.0 */
function digAddr(prefix, startByte, chIndex0) {
  const b = Number(startByte) + Math.floor(chIndex0 / 8);
  const bit = chIndex0 % 8;
  return `${prefix}${b}.${bit}`;
}

/** 模拟量：起始字节 + 通道 → IW64 / QW80 */
function anaAddr(prefix, startByte, chIndex0) {
  const b = Number(startByte) + chIndex0 * 2;
  return `${prefix}${b}`;
}

function slotAddrSummary(kind, s) {
  const n = Math.min(Number(s.channel_count) || 0, 64);
  if (n <= 0) return "—";
  if (kind === "di") {
    return `${digAddr("%I", s.start_addr, 0)} … ${digAddr("%I", s.start_addr, n - 1)}`;
  }
  if (kind === "dq") {
    return `${digAddr("%Q", s.start_addr, 0)} … ${digAddr("%Q", s.start_addr, n - 1)}`;
  }
  if (kind === "ai") {
    return `${anaAddr("%IW", s.start_addr, 0)} … ${anaAddr("%IW", s.start_addr, n - 1)}`;
  }
  return `${anaAddr("%QW", s.start_addr, 0)} … ${anaAddr("%QW", s.start_addr, n - 1)}`;
}

function slotAddrList(kind, s, maxShow = 16) {
  const n = Math.min(Number(s.channel_count) || 0, 64);
  const parts = [];
  const show = Math.min(n, maxShow);
  for (let i = 0; i < show; i++) {
    if (kind === "di") parts.push(digAddr("%I", s.start_addr, i));
    else if (kind === "dq") parts.push(digAddr("%Q", s.start_addr, i));
    else if (kind === "ai") parts.push(anaAddr("%IW", s.start_addr, i));
    else parts.push(anaAddr("%QW", s.start_addr, i));
  }
  if (n > maxShow) parts.push("…");
  return parts.join(", ");
}

function setStatus(text, cls) {
  const el = $("connStatus");
  el.textContent = text;
  el.className = "status " + (cls || "");
}

function refreshConnStatus() {
  if (plcConnected) {
    setStatus(plcMock ? "已连接 (Mock)" : "已连接", plcMock ? "mock" : "ok");
  } else {
    setStatus("未连接");
  }
}

function applyConnFromSnap(snap) {
  if (typeof snap?.connected === "boolean") {
    plcConnected = snap.connected;
    plcMock = !!snap.mock;
    refreshConnStatus();
  }
}

/** 按钮绿灯只看 Force 位图（与点按/复位一致） */
function dqBitsForSlot(slot, forceBits) {
  const f = Array.isArray(forceBits) ? forceBits : lastDqForce;
  return Array.isArray(f) ? Number(f[slot - 1]) || 0 : 0;
}

function clearDqUi(forceBits) {
  dqHoldUntil = 0;
  dqAllowZeroFromServer = true;
  lastDqForce = Array.isArray(forceBits) ? forceBits.slice() : Array(20).fill(0);
  lastDqQMasks = Array(20).fill(0);
  updateDqButtonStates(lastDqForce);
  const st = $("dqStatus");
  if (st) st.textContent = "已复位";
}

function forceSum(arr) {
  if (!Array.isArray(arr)) return 0;
  return arr.reduce((a, b) => a + (Number(b) || 0), 0);
}


async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const msg = Array.isArray(detail)
      ? detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
      : detail || JSON.stringify(data) || res.statusText;
    throw new Error(msg);
  }
  return data;
}

function showPage(name) {
  document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.page === name));
  $("page-" + name).classList.add("active");
  if (name === "dq") {
    ensureDqSlotOptions();
    buildDqGrid(lastDqForce);
  }
  if (name === "config") renderSlots();
  if (name === "di") renderDiAddrTable(lastDiStates);
  if (name === "ai") renderAiTable(lastAiValues);
  if (name === "aq") renderAqTable(lastAqValues);
}

async function refreshConfigList() {
  const { items } = await api("/api/configs");
  const sel = $("cfgList");
  sel.innerHTML = items.map((n) => `<option value="${n}">${n}</option>`).join("");
}

async function loadCabinet(name) {
  cabinet = await api("/api/configs/" + encodeURIComponent(name));
  $("cfgName").value = name;
  $("plcIp").value = cabinet.plc?.ip || "192.168.0.1";
  $("plcRack").value = cabinet.plc?.rack ?? 0;
  $("plcSlot").value = cabinet.plc?.slot ?? 1;
  $("dbConfig").value = cabinet.plc?.db_config ?? 10;
  $("dbRuntime").value = cabinet.plc?.db_runtime ?? 11;
  dqBuiltKey = "";
  renderSlots();
  ensureDqSlotOptions();
}

function renderSlots() {
  if (!cabinet) return;
  const host = $("slotEditor");
  const list = cabinet[currentKind] || [];
  const ana = currentKind === "ai" || currentKind === "aq";
  host.innerHTML = list
    .map((s) => {
      const preview = s.enable
        ? `<div class="addr-preview">地址: ${slotAddrSummary(currentKind, s)}　|　${slotAddrList(currentKind, s, 8)}</div>`
        : `<div class="addr-preview" style="color:var(--muted)">未启用</div>`;
      return `<div class="slot-card ${ana ? "ana" : ""}" data-slot="${s.slot}">
        <label class="check"><input type="checkbox" data-f="enable" ${s.enable ? "checked" : ""}/> #${s.slot}</label>
        <label>名称<input data-f="name" value="${s.name || ""}"/></label>
        <label>起始字节<input data-f="start_addr" type="number" value="${s.start_addr}"/></label>
        <label>通道数<input data-f="channel_count" type="number" value="${s.channel_count}"/></label>
        ${
          ana
            ? `<label>Raw满<input data-f="raw_full" type="number" value="${s.raw_full ?? 27648}"/></label>
               <label>下限mA<input data-f="eng_min_ma" type="number" step="0.1" value="${s.eng_min_ma ?? 4}"/></label>
               <label>上限mA<input data-f="eng_full_ma" type="number" step="0.1" value="${s.eng_full_ma ?? 20}"/></label>`
            : `<span></span>`
        }
        ${preview}
      </div>`;
    })
    .join("");

  host.querySelectorAll(".slot-card").forEach((card) => {
    card.querySelectorAll("[data-f]").forEach((inp) => {
      inp.addEventListener("change", () => {
        const slot = Number(card.dataset.slot);
        const item = cabinet[currentKind].find((x) => x.slot === slot);
        const f = inp.dataset.f;
        if (f === "enable") item.enable = inp.checked;
        else if (f === "name") item.name = inp.value;
        else if (f === "eng_full_ma" || f === "eng_min_ma") item[f] = Number(inp.value);
        else item[f] = Number(inp.value);
        if (currentKind === "dq") {
          dqBuiltKey = "";
          ensureDqSlotOptions();
        }
        renderSlots();
        renderAddrMapTable();
      });
    });
  });
  renderAddrMapTable();
}

function renderAddrMapTable() {
  const tb = $("addrMapTable")?.querySelector("tbody");
  if (!tb) return;
  if (!cabinet) {
    tb.innerHTML = `<tr><td colspan="7">配置未加载，请先在上方选择并加载配置</td></tr>`;
    return;
  }
  const rows = [];
  let anyOn = false;
  for (const kind of ["di", "dq", "ai", "aq"]) {
    const label = kind.toUpperCase();
    for (const s of cabinet[kind] || []) {
      const on = !!s.enable;
      if (on) anyOn = true;
      rows.push(`<tr style="${on ? "" : "opacity:0.45"}">
        <td>${label}</td>
        <td>${s.slot}</td>
        <td>${s.name || "—"}</td>
        <td>${s.start_addr}</td>
        <td>${s.channel_count}</td>
        <td><code>${on ? slotAddrSummary(kind, s) : "（未启用）"}</code></td>
        <td><code>${on ? slotAddrList(kind, s, 32) : "—"}</code></td>
      </tr>`);
    }
  }
  if (!rows.length) {
    tb.innerHTML = `<tr><td colspan="7">配置中无槽位数据</td></tr>`;
    return;
  }
  tb.innerHTML =
    rows.join("") +
    (anyOn
      ? ""
      : `<tr><td colspan="7">尚未勾选启用：请在上方勾选模块后，对应行会显示 IO 地址</td></tr>`);
}


function collectPlcIntoCabinet() {
  if (!cabinet) return;
  cabinet.plc = {
    ...(cabinet.plc || {}),
    ip: $("plcIp").value.trim(),
    rack: Number($("plcRack").value),
    slot: Number($("plcSlot").value),
    db_config: Number($("dbConfig").value),
    db_runtime: Number($("dbRuntime").value),
    poll_ms: cabinet.plc?.poll_ms ?? 50,
  };
}

function ensureDqSlotOptions() {
  if (!cabinet) return;
  const sel = $("dqSlot");
  const prev = sel.value;
  const enabled = (cabinet.dq || []).filter((s) => s.enable);
  const html = enabled.length
    ? enabled
        .map((s) => `<option value="${s.slot}">槽${s.slot} ${s.name || ""} (${s.channel_count}点)</option>`)
        .join("")
    : `<option value="">无启用 DQ 槽</option>`;
  if (sel.dataset.sig !== html) {
    sel.innerHTML = html;
    sel.dataset.sig = html;
    if (prev && [...sel.options].some((o) => o.value === prev)) sel.value = prev;
  }
}

function updateDqButtonStates(forceBits) {
  const slot = Number($("dqSlot").value);
  if (!slot) return;
  if (Array.isArray(forceBits)) lastDqForce = forceBits.slice();
  const bits = dqBitsForSlot(slot, lastDqForce);
  $("dqGrid").querySelectorAll("button[data-ch]").forEach((btn) => {
    const i = Number(btn.dataset.ch) - 1;
    const on = !!(bits & (1 << i));
    btn.classList.toggle("on", on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  });
  const onList = [];
  $("dqGrid").querySelectorAll("button.on").forEach((b) => onList.push(b.dataset.ch));
  $("dqStatus").textContent = onList.length
    ? `本槽已强制: 通道 ${onList.join(", ")}（Force=${bits}）`
    : `本槽无强制（Force=${bits}）`;
}

function buildDqGrid(forceBits) {
  if (!cabinet) return;
  ensureDqSlotOptions();
  const slot = Number($("dqSlot").value);
  const conf = (cabinet.dq || []).find((s) => s.slot === slot);
  const grid = $("dqGrid");
  if (!conf) {
    grid.innerHTML = "<p class='hint'>请先在配置页启用 DQ 模块并保存</p>";
    dqBuiltKey = "";
    return;
  }
  const key = `${slot}:${conf.channel_count}:${conf.start_addr}`;
  if (key !== dqBuiltKey) {
    const n = Math.min(conf.channel_count, 32);
    const start = Number(conf.start_addr) || 0;
    grid.innerHTML = Array.from({ length: n }, (_, i) => {
      const addr = digAddr("%Q", start, i);
      return `<button type="button" data-ch="${i + 1}" title="${addr}" aria-pressed="false"><span>${i + 1}</span><span class="addr">${addr}</span></button>`;
    }).join("");
    $("dqAddrHint").textContent =
      `本槽起始字节 ${start} → ${slotAddrSummary("dq", conf)}；点按钮强制对应 %Q 地址（需 Config.Enable 且 FC 已运行）`;
    grid.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const ch = Number(btn.dataset.ch);
        const cur = dqBitsForSlot(slot, lastDqForce);
        const mask = 1 << (ch - 1);
        const turnOn = !(cur & mask);
        if (!Array.isArray(lastDqForce)) lastDqForce = Array(20).fill(0);
        lastDqForce = lastDqForce.slice();
        if (turnOn) lastDqForce[slot - 1] = (Number(lastDqForce[slot - 1]) || 0) | mask;
        else lastDqForce[slot - 1] = (Number(lastDqForce[slot - 1]) || 0) & ~mask;
        dqHoldUntil = Date.now() + 3000;
        dqAllowZeroFromServer = false;
        updateDqButtonStates(lastDqForce);
        btn.disabled = true;
        try {
          const r = await api("/api/dq/set", {
            method: "POST",
            body: JSON.stringify({ slot, channel: ch, value: turnOn }),
          });
          if (Array.isArray(r.dq_force)) lastDqForce = r.dq_force.slice();
          dqHoldUntil = Date.now() + 3000;
          dqAllowZeroFromServer = false;
          updateDqButtonStates(lastDqForce);
          $("dqStatus").textContent = turnOn
            ? `已强制通道 ${ch} 为高`
            : `已关闭通道 ${ch}`;
          if (turnOn) Voice.sayChannel(ch);
        } catch (e) {
          if (turnOn) lastDqForce[slot - 1] = (Number(lastDqForce[slot - 1]) || 0) & ~mask;
          else lastDqForce[slot - 1] = (Number(lastDqForce[slot - 1]) || 0) | mask;
          updateDqButtonStates(lastDqForce);
          alert("DQ 操作失败: " + e.message + "\n请先在「连接」页连接（可用 Mock）。");
        } finally {
          btn.disabled = false;
        }
      });
    });
    dqBuiltKey = key;
  }
  updateDqButtonStates(forceBits);
}

function renderDiChips(states) {
  lastDiStates = states || {};
  const host = $("diChips");
  const entries = Object.entries(lastDiStates).sort((a, b) => Number(a[0]) - Number(b[0]));
  if (!entries.length) {
    host.innerHTML = "";
  } else {
    host.innerHTML = entries
      .map(([ch, on]) => `<span class="${on ? "on" : ""}" title="全局通道 ${ch}">${ch}</span>`)
      .join("");
  }
  renderDiAddrTable(lastDiStates);
}

function renderDiAddrTable(states) {
  const tb = $("diAddrTable")?.querySelector("tbody");
  if (!tb || !cabinet) return;
  const rows = [];
  let g = 0;
  for (const s of [...(cabinet.di || [])].sort((a, b) => a.slot - b.slot)) {
    if (!s.enable) continue;
    const n = Number(s.channel_count) || 0;
    for (let i = 0; i < n; i++) {
      g += 1;
      const addr = digAddr("%I", s.start_addr, i);
      const on = !!(states && states[g]);
      rows.push(`<tr>
        <td>${g}</td><td>${s.slot}</td><td>${i + 1}</td>
        <td><code>${addr}</code></td>
        <td style="color:${on ? "var(--ok)" : "var(--muted)"}">${on ? "ON" : "OFF"}</td>
      </tr>`);
    }
  }
  tb.innerHTML = rows.join("") || `<tr><td colspan="5">无启用 DI</td></tr>`;
}

function renderAiTable(values) {
  lastAiValues = values || {};
  const tb = $("aiTable").querySelector("tbody");
  if (!cabinet) {
    tb.innerHTML = "";
    return;
  }
  const rows = [];
  let g = 0;
  for (const s of [...(cabinet.ai || [])].sort((a, b) => a.slot - b.slot)) {
    if (!s.enable) continue;
    const n = Number(s.channel_count) || 0;
    for (let i = 0; i < n; i++) {
      g += 1;
      const addr = anaAddr("%IW", s.start_addr, i);
      const ma = lastAiValues[String(g)];
      rows.push(`<tr><td>${g}</td><td><code>${addr}</code></td><td>${ma == null ? "—" : Number(ma).toFixed(2)}</td></tr>`);
    }
  }
  tb.innerHTML = rows.join("") || `<tr><td colspan="3">无启用 AI</td></tr>`;
}

function renderAqTable(values) {
  lastAqValues = values || [];
  const tb = $("aqTable").querySelector("tbody");
  if (!cabinet) {
    tb.innerHTML = "";
    return;
  }
  const rows = [];
  let g = 0;
  for (const s of [...(cabinet.aq || [])].sort((a, b) => a.slot - b.slot)) {
    if (!s.enable) continue;
    const n = Number(s.channel_count) || 0;
    for (let i = 0; i < n; i++) {
      g += 1;
      const addr = anaAddr("%QW", s.start_addr, i);
      const ma = lastAqValues[g - 1];
      rows.push(`<tr><td>${g}</td><td><code>${addr}</code></td><td>${ma == null ? "—" : Number(ma).toFixed(2)}</td></tr>`);
    }
  }
  tb.innerHTML = rows.join("") || `<tr><td colspan="3">无启用 AQ</td></tr>`;
}


async function poll() {
  try {
    const snap = await api("/api/snapshot");
    applyConnFromSnap(snap);
    if (snap.active_di != null) {
      $("diHero").textContent = String(snap.active_di);
    }
    if (snap.active_ai) {
      $("aiHero").textContent = String(snap.active_ai.channel);
      $("aiText").textContent = `通道 ${snap.active_ai.channel}，${snap.active_ai.ma.toFixed(1)} mA`;
    }
    renderDiChips(snap.di_states);
    renderAiTable(snap.ai_values);
    renderAqTable(snap.aq_values);
    if (Array.isArray(snap.dq_force)) {
      const snapZ = forceSum(snap.dq_force) === 0;
      const localZ = forceSum(lastDqForce) === 0;
      const pastHold = Date.now() >= dqHoldUntil;
      // 拒绝用服务器全 0 覆盖本地非 0（除非刚复位）
      if (pastHold && (!snapZ || localZ || dqAllowZeroFromServer)) {
        lastDqForce = snap.dq_force.slice();
        if (snapZ) dqAllowZeroFromServer = false;
      }
    }
    if (Array.isArray(snap.dq_q_masks)) lastDqQMasks = snap.dq_q_masks;
    if (document.getElementById("page-dq").classList.contains("active")) {
      updateDqButtonStates(lastDqForce);
    }
    for (const ev of snap.events || []) {
      if (ev.kind === "di") {
        $("diHero").textContent = String(ev.channel);
        $("diText").textContent = ev.text;
      }
      if (ev.kind === "ai") {
        $("aiHero").textContent = String(ev.channel);
        $("aiText").textContent = ev.text;
      }
      Voice.announce(ev);
    }
    if (snap.error) $("connectMsg").textContent = "扫描: " + snap.error;
  } catch {
    /* 网络抖动不改连接角标 */
  }
}

document.getElementById("tabs").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-page]");
  if (btn) showPage(btn.dataset.page);
});

document.querySelector(".slot-tools").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-kind]");
  if (!btn) return;
  currentKind = btn.dataset.kind;
  document.querySelectorAll(".slot-tools button").forEach((b) => b.classList.toggle("active", b === btn));
  renderSlots();
});

$("btnConnect").onclick = async () => {
  collectPlcIntoCabinet();
  try {
    const r = await api("/api/connect", {
      method: "POST",
      body: JSON.stringify({
        ip: $("plcIp").value.trim(),
        rack: Number($("plcRack").value),
        slot: Number($("plcSlot").value),
        db_config: Number($("dbConfig").value),
        db_runtime: Number($("dbRuntime").value),
        mock: $("mockMode").checked,
      }),
    });
    plcConnected = r.connected !== false;
    plcMock = !!r.mock;
    refreshConnStatus();
    let msg = r.mock ? "Mock 已连接（可在 DI/AI/DQ 页测试）" : "PLC 已连接";
    if (r.db_config_size != null) {
      msg += ` | DB${$("dbConfig").value}长度=${r.db_config_size}, DB${$("dbRuntime").value}长度=${r.db_runtime_size}`;
    }
    if (r.config_error) msg += " | " + r.config_error;
    $("connectMsg").textContent = msg;
    if (cabinet) {
      await api("/api/configs", {
        method: "POST",
        body: JSON.stringify({ name: $("cfgName").value.trim(), cabinet, push_to_plc: true }),
      });
    }
  } catch (e) {
    plcConnected = false;
    refreshConnStatus();
    $("connectMsg").textContent = e.message;
  }
};

$("btnDisconnect").onclick = async () => {
  // 先更新角标，再请求后端（避免 S7 断开阻塞导致一直显示已连接）
  plcConnected = false;
  plcMock = false;
  refreshConnStatus();
  clearDqUi(Array(20).fill(0));
  $("connectMsg").textContent = "正在断开…";
  try {
    await api("/api/disconnect", { method: "POST", body: "{}" });
    $("connectMsg").textContent = "已断开";
  } catch (e) {
    $("connectMsg").textContent = "断开失败: " + e.message;
  }
};

$("btnLoadCfg").onclick = async () => {
  await loadCabinet($("cfgList").value);
};

$("btnSaveCfg").onclick = async () => {
  collectPlcIntoCabinet();
  const name = $("cfgName").value.trim() || "cabinet";
  try {
    const r = await api("/api/configs", {
      method: "POST",
      body: JSON.stringify({ name, cabinet, push_to_plc: true }),
    });
    await refreshConfigList();
    dqBuiltKey = "";
    ensureDqSlotOptions();
    alert(r.pushed ? "已保存并下发到 PLC" : "已保存到本地（未连接则未下发）");
  } catch (e) {
    alert(e.message);
  }
};

$("btnDqResetSlot").onclick = async () => {
  const slot = Number($("dqSlot").value);
  try {
    const r = await api("/api/dq/reset", { method: "POST", body: JSON.stringify({ slot }) });
    clearDqUi(r.dq_force);
    $("dqStatus").textContent = `槽 ${slot} 已复位`;
  } catch (e) {
    alert("DQ 操作失败: " + e.message);
  }
};

$("btnDqResetAll").onclick = async () => {
  try {
    const r = await api("/api/dq/reset", { method: "POST", body: JSON.stringify({}) });
    clearDqUi(r.dq_force);
    $("dqStatus").textContent = "全部 DQ 已复位";
  } catch (e) {
    alert("DQ 操作失败: " + e.message);
  }
};

$("btnMockDi").onclick = async () => {
  const s = (cabinet?.di || []).find((x) => x.enable);
  if (!s) return alert("无启用 DI 槽");
  await api("/api/mock/di", {
    method: "POST",
    body: JSON.stringify({ start_addr: s.start_addr, bit: 0, value: false }),
  });
  setTimeout(() => {
    api("/api/mock/di", {
      method: "POST",
      body: JSON.stringify({ start_addr: s.start_addr, bit: 0, value: true }),
    });
  }, 80);
};

$("btnMockAi").onclick = async () => {
  const s = (cabinet?.ai || []).find((x) => x.enable);
  if (!s) return alert("无启用 AI 槽");
  // 4~20mA：raw=0→4mA；模拟约 5mA 便于触发变化播报
  await api("/api/mock/ai", {
    method: "POST",
    body: JSON.stringify({
      start_addr: s.start_addr,
      raw: Math.round(((5 - 4) / 16) * 27648),
    }),
  });
};

$("dqSlot").onchange = () => {
  dqBuiltKey = "";
  buildDqGrid(lastDqForce);
};

(async function init() {
  document.querySelector('.slot-tools button[data-kind="di"]').classList.add("active");
  await Voice.preload();
  await refreshConfigList();
  const name = $("cfgList").value || "example_cabinet";
  try {
    await loadCabinet(name);
  } catch {
    /* empty */
  }
  pollTimer = setInterval(poll, 100);
  poll();
})();
