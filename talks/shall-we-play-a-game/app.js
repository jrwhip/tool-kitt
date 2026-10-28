// Shall We Play a Game? — deck navigation + recording replays.
// No framework, no build, no server: recordings load from replays/*.js (window.KITT_REPLAYS).

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const REPLAYS = () => window.KITT_REPLAYS || {};

/* ─────────────────────────── backdrop ─────────────────────────── */

(function stars() {
  const host = $(".sky__stars");
  if (!host) return;
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const frag = document.createDocumentFragment();
  for (let i = 0; i < 70; i++) {
    const s = document.createElement("i");
    const r = rnd();
    if (r > 0.93) s.className = "spark";
    else if (r > 0.8) s.className = "big";
    s.style.left = `${(rnd() * 100).toFixed(2)}%`;
    s.style.top = `${(rnd() * 100).toFixed(2)}%`;
    s.style.opacity = (0.35 + rnd() * 0.6).toFixed(2);
    frag.append(s);
  }
  host.append(frag);
})();

/* ─────────────────────────── deck ─────────────────────────── */

const deck = {
  slides: $$(".slide"),
  index: 0,
  init() {
    $("#slide-total").textContent = String(this.slides.length).padStart(2, "0");
    const fromHash = parseInt(location.hash.slice(1), 10);
    this.go(Number.isFinite(fromHash) ? fromHash - 1 : 0, { instant: true });
    addEventListener("hashchange", () => {
      const n = parseInt(location.hash.slice(1), 10) - 1;
      if (Number.isFinite(n) && n !== this.index) this.go(n);
    });
  },
  go(n, { instant = false } = {}) {
    const next = Math.max(0, Math.min(this.slides.length - 1, n));
    this.slides.forEach((s, i) => s.classList.toggle("is-active", i === next));
    this.index = next;
    history.replaceState(null, "", `#${next + 1}`);
    $("#slide-current").textContent = String(next + 1).padStart(2, "0");
    $("#section-label").textContent = this.slides[next].dataset.section ?? "";
    $("#progress").style.width = `${((next + 1) / this.slides.length) * 100}%`;
    notes.render(this.slides[next]);
    replays.stopAll();
    const player = replays.for(this.slides[next]);
    if (player && !player.played) setTimeout(() => player.play(), 700);
    if (instant) {
      this.slides[next].style.transition = "none";
      requestAnimationFrame(() => (this.slides[next].style.transition = ""));
    }
  },
  next() { this.go(this.index + 1); },
  prev() { this.go(this.index - 1); },
};

const notes = {
  on: false,
  panel: $("#notes-panel"),
  toggle() { this.on = !this.on; this.render(deck.slides[deck.index]); },
  render(slide) {
    const text = $(".notes", slide)?.textContent.trim();
    this.panel.hidden = !(this.on && text);
    this.panel.textContent = text ?? "";
  },
};

(function clock() {
  let start = Date.now();
  const el = $("#clock");
  const tick = () => {
    const s = Math.floor((Date.now() - start) / 1000);
    el.textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  };
  setInterval(tick, 1000);
  el.addEventListener("click", () => { start = Date.now(); tick(); });
  el.title = "talk clock. click to reset";
})();

function toast(msg, ms = 2600) {
  let el = $(".toast");
  if (!el) { el = document.createElement("div"); el.className = "toast"; document.body.appendChild(el); }
  el.textContent = msg;
  el.classList.add("is-on");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("is-on"), ms);
}

/* ─────────────────────────── robot images ─────────────────────────── */
// Each <img data-robot="scout"> loads images/<name>.png if present. Missing art shows a labelled
// placeholder so the deck is presentable before the art lands.

function wireRobots() {
  for (const img of $$("img[data-robot]")) {
    const name = img.dataset.robot;
    img.src = `images/${name}.jpg`;
    img.alt = img.alt || `${name} robot`;
    img.addEventListener("error", () => {
      const ph = document.createElement("div");
      ph.className = "robot--missing";
      ph.innerHTML = `<b></b>drop images/${name}.jpg here`;
      $("b", ph).textContent = img.dataset.caption || name;
      img.replaceWith(ph);
    }, { once: true });
  }
}

/* ─────────────────────────── replay player ─────────────────────────── */

const TOOL_VERB = {
  Read: "read", Glob: "list", Grep: "search", Edit: "edit", Write: "write", MultiEdit: "edit", Bash: "run",
  Skill: "skill", TodoWrite: "todo", AskUserQuestion: "ask", Task: "dispatch",
};
const verbFor = (tool) => TOOL_VERB[tool] ?? (tool.startsWith("kitt:") ? "kitt" : tool.toLowerCase());
const classFor = (tool) => tool.startsWith("kitt:") ? "kitt" : tool.toLowerCase();
const HOME = /\/home\/[a-z0-9_-]+/gi;
const ANSI = /\u001b\[[0-9;?]*[A-Za-z]/g;  // terminal color codes captured from tool output
const tidy = (s) => (s || "").replace(ANSI, "").replace(HOME, "~");
// MCP results arrive as {"result": "..."} JSON; show the inner text, even when the recording truncated it.
function unwrapOutput(text) {
  const t = tidy(text);
  if (!t.startsWith('{"result"')) return t;
  try { const o = JSON.parse(t); if (typeof o.result === "string") return o.result; } catch { /* truncated */ }
  return t.replace(/^\{"result":\s*"/, "").replace(/\\n/g, "\n").replace(/\\"/g, '"').replace(/"\}?$/, "");
}

// Plays one recording (or a slice of it) as a terminal activity log. Gaps between events are
// capped so a ten-minute run narrates in a couple of minutes without changing the order of events.
class Player {
  static MAX_GAP_MS = 1200;
  constructor(root) {
    this.root = root;
    this.key = root.dataset.replay;
    this.fromAgent = root.dataset.fromAgent || null; // start at the first `agent` event naming this role
    this.toAgent = root.dataset.toAgent || null;     // stop before the first `agent` event naming this role
    this.rec = null;
    this.abort = null;
    this.played = false;
    this.speed = 1;
    this.watch = $$("[data-watch]", root);
    this.el("play")?.addEventListener("click", () => this.play());
    this.el("skip")?.addEventListener("click", () => this.finish());
  }
  // Controls (play, skip, model tag) live in the slide header, outside the replay box, so search the whole slide.
  el(name) { return $(`[data-r="${name}"]`, this.root.closest(".slide") ?? this.root); }
  load() {
    this.rec = REPLAYS()[this.key] ?? null;
    if (this.rec) this.render();
    else this.el("log")?.replaceChildren(Object.assign(document.createElement("li"), {
      className: "log__item log__item--text", textContent: `No recording yet. Run record.py and reload; it writes replays/${this.key}.js.`,
    }));
    return this;
  }
  slice() {
    const evs = this.rec.events;
    let start = 0, end = evs.length;
    if (this.fromAgent) {
      const i = evs.findIndex((e) => e.kind === "agent" && e.agent_name.includes(this.fromAgent));
      if (i >= 0) start = i;
    }
    if (this.toAgent) {
      const i = evs.findIndex((e, idx) => idx > start && e.kind === "agent" && e.agent_name.includes(this.toAgent));
      if (i >= 0) end = i;
    }
    return evs.slice(start, end);
  }
  render() {
    const r = this.rec;
    if (this.el("model")) this.el("model").textContent = `${r.harness} · ${r.model || "claude"}`;
    if (this.el("prompt")) {
      // Show the first line (the command or the one-sentence ask); the operator's pre-answers stay in the tooltip.
      const first = r.prompt.split("\n").map((l) => l.trim()).find(Boolean) ?? "";
      this.el("prompt").textContent = first.length > 300 ? first.slice(0, 300) + " …" : first;
      this.el("prompt").title = r.prompt;
    }
    this.reset();
  }
  reset() {
    this.el("log")?.replaceChildren();
    this.el("files")?.replaceChildren();
    this.counts = { tools: 0, reads: new Set(), writes: new Set(), agents: 0 };
    this.set("tools", "0"); this.set("reads", "0"); this.set("writes", "0"); this.set("agents", "0");
    this.set("time", "0.0s"); this.set("cost", "—"); this.set("tests", "—");
    this.watch.forEach((w) => w.classList.remove("is-hit"));
    this.root.classList.remove("is-running");
  }
  set(name, v) { const el = this.el(name); if (el) el.textContent = v; }
  apply(ev) {
    const log = this.el("log");
    if (!log) return;
    const li = document.createElement("li");
    if (ev.agent) li.dataset.agent = ev.agent;
    if (ev.kind === "tool") {
      this.counts.tools++;
      if (ev.tool === "Read") this.counts.reads.add(ev.detail);
      if (["Edit", "Write", "MultiEdit"].includes(ev.tool)) this.counts.writes.add(ev.detail);
      li.className = `log__item log__item--${classFor(ev.tool)}`;
      li.innerHTML = `<span class="log__verb"></span><code class="log__detail"></code>`;
      $(".log__verb", li).textContent = verbFor(ev.tool);
      $(".log__detail", li).textContent = ev.tool.startsWith("kitt:") ? `${ev.tool.slice(5)} ${tidy(ev.detail)}` : tidy(ev.detail);
    } else if (ev.kind === "agent") {
      this.counts.agents++;
      li.className = "log__item log__item--agent";
      li.innerHTML = `<b></b><span></span>`;
      $("b", li).textContent = ev.agent_name;
      $("span", li).textContent = ev.detail;
    } else if (ev.kind === "text") {
      li.className = "log__item log__item--text";
      li.textContent = tidy(ev.text.length > 700 ? ev.text.slice(0, 700) + " …" : ev.text);
    } else if (ev.kind === "output") {
      // Permission-system chatter from the recording harness is not part of the story; keep it out of the log.
      if (/^(This Bash command contains multiple operations|A variable in this command can't be checked)/.test(ev.output)) return;
      li.className = "log__item log__item--output" + (ev.error ? " is-error" : "");
      li.textContent = unwrapOutput(ev.output);
    } else if (ev.kind === "result") {
      li.className = "log__item log__item--result";
      // The orchestrator's final message starts by echoing the requirement for the review gate; show its result section.
      const txt = this.rec.finalText || ev.text || "";  // the event text is capped by the recorder; finalText is whole
      const at = txt.search(/\n## (Result|Outcome|Summary)/i);
      li.textContent = tidy((at >= 0 ? txt.slice(at + 1) : txt).slice(0, 900));
      if (ev.cost != null) this.set("cost", `$${Number(ev.cost).toFixed(2)}`);
      const t = this.rec.after?.tests;
      if (t?.summary) this.set("tests", t.summary.replace(/\u001b\[[0-9;]*m/g, "").replace(/^\s*Tests\s*/, "").replace(/\s*\(.*$/, ""));
      else if (t?.ran) this.set("tests", t.exit === 0 ? "pass" : "FAIL");
      const files = this.el("files");
      if (files) for (const f of this.rec.after?.changed ?? []) files.append(Object.assign(document.createElement("li"), { textContent: f }));
    } else {
      return;
    }
    log.append(li);
    this.hitWatch(ev);
    this.set("tools", this.counts.tools);
    this.set("reads", this.counts.reads.size);
    this.set("writes", this.counts.writes.size);
    this.set("agents", this.counts.agents);
    log.scrollTop = log.scrollHeight;
  }
  hitWatch(ev) {
    const hay = `${ev.tool ?? ""} ${ev.detail ?? ""} ${ev.text ?? ""} ${ev.output ?? ""} ${ev.agent_name ?? ""}`.toLowerCase();
    for (const w of this.watch) {
      if (w.classList.contains("is-hit")) continue;
      const needles = w.dataset.watch.split("|").map((s) => s.trim().toLowerCase()).filter(Boolean);
      if (needles.some((n) => hay.includes(n))) w.classList.add("is-hit");
    }
  }
  async play() {
    if (!this.rec) { toast(`No recording for "${this.key}" yet.`); return; }
    this.abort?.abort();
    this.abort = new AbortController();
    const { signal } = this.abort;
    this.reset();
    this.root.classList.add("is-running");
    this.played = true;
    const evs = this.slice();
    let clock = 0, prevT = evs[0]?.t ?? 0;
    const t0 = performance.now();
    for (const ev of evs) {
      if (signal.aborted) return;
      clock += Math.min(Math.max(ev.t - prevT, 0), Player.MAX_GAP_MS);
      prevT = ev.t;
      const wait = t0 + clock / this.speed - performance.now();
      if (wait > 4) await sleep(wait);
      if (signal.aborted) return;
      this.apply(ev);
      if (ev.kind !== "result") this.set("time", `${(ev.t / 1000).toFixed(1)}s`);
    }
    this.root.classList.remove("is-running");
  }
  finish() {
    if (!this.rec) return;
    this.abort?.abort();
    this.reset();
    this.played = true;
    for (const ev of this.slice()) this.apply(ev);
    const last = this.rec.events.at(-1);
    if (last) this.set("time", `${(last.t / 1000).toFixed(0)}s`);
  }
  stop() { this.abort?.abort(); this.root.classList.remove("is-running"); }
}

const replays = {
  players: new Map(),
  init() {
    for (const el of $$("[data-replay]")) {
      const slide = el.closest(".slide");
      this.players.set(slide, new Player(el).load());
    }
  },
  for(slide) { return this.players.get(slide) ?? null; },
  stopAll() { this.players.forEach((p) => p.stop()); },
  setSpeed(x) { this.players.forEach((p) => (p.speed = x)); toast(`replay speed ${x}×`); },
};

/* ─────────────────────────── stats from recordings ─────────────────────────── */
// <span data-stat="naked.cost"> fills from the recording so no number on a slide is typed by hand.

function fillStats() {
  for (const el of $$("[data-stat]")) {
    const [key, field] = el.dataset.stat.split(".");
    const r = REPLAYS()[key];
    if (!r) continue;
    let v = "";
    switch (field) {
      case "cost": v = r.usage?.total_cost_usd != null ? `$${r.usage.total_cost_usd.toFixed(2)}` : ""; break;
      case "minutes": {
        const ms = r.usage?.duration_ms;
        v = !ms ? "" : ms < 90000 ? `${Math.round(ms / 1000)} seconds` : `${(ms / 60000).toFixed(1)} minutes`;
        break;
      }
      case "turns": v = r.usage?.num_turns ?? ""; break;
      case "tools": v = r.events.filter((e) => e.kind === "tool").length; break;
      case "agents": v = r.events.filter((e) => e.kind === "agent").length; break;
      case "files": v = r.after?.changed?.length ?? ""; break;
      case "tests": v = (r.after?.tests?.summary ?? "").replace(/\u001b\[[0-9;]*m/g, "").replace(/^\s*Tests\s*/, "").replace(/\s*\(.*$/, ""); break;
      case "model": v = r.model; break;
    }
    if (v !== "") el.textContent = v;
  }
}

/* ─────────────────────────── keys ─────────────────────────── */

const typing = (e) => ["TEXTAREA", "INPUT", "SELECT"].includes(e.target.tagName);
addEventListener("keydown", (e) => {
  if (e.key === "Escape") { $("#help").hidden = true; return; }
  if (typing(e) || e.metaKey || e.ctrlKey || e.altKey) return;
  switch (e.key) {
    case "ArrowRight": case "ArrowDown": case " ": case "PageDown": e.preventDefault(); deck.next(); break;
    case "ArrowLeft": case "ArrowUp": case "Backspace": case "PageUp": e.preventDefault(); deck.prev(); break;
    case "Home": deck.go(0); break;
    case "End": deck.go(deck.slides.length - 1); break;
    case "r": case "R": { const p = replays.for(deck.slides[deck.index]); if (p) p.play(); else toast("No recording on this slide."); break; }
    case "s": case "S": { const p = replays.for(deck.slides[deck.index]); if (p) p.finish(); break; }
    case "1": replays.setSpeed(1); break;
    case "2": replays.setSpeed(2); break;
    case "3": replays.setSpeed(4); break;
    case "n": case "N": notes.toggle(); break;
    case "f": case "F": document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen(); break;
    case "?": $("#help").hidden = !$("#help").hidden; break;
  }
});

/* ─────────────────────────── boot ─────────────────────────── */

window.talk = { deck, replays, notes };
wireRobots();
replays.init();
fillStats();
deck.init();
