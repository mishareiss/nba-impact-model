/* NBA Shot Quality & Impact: static dashboard.
 * Reads precomputed JSON from ./data (see scripts/export_static.py). No backend. */
(() => {
  "use strict";

  // ------------------------------------------------------------------ utils
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const MINUS = "−";
  const signed = (v, d = 1) => { if (v == null || isNaN(v)) return "–"; const t = Math.abs(v).toFixed(d); return +t === 0 ? t : (v > 0 ? "+" : MINUS) + t; };
  const pct = (v, d = 1) => (v == null ? "–" : (v * 100).toFixed(d) + "%");
  const fmtInt = (v) => (v == null ? "–" : Math.round(v).toLocaleString("en-US"));
  const compact = (v) => (v >= 1e6 ? (v / 1e6).toFixed(2) + "M" : v >= 1e3 ? Math.round(v / 1e3) + "K" : String(v));
  const shortSeason = (s) => s.slice(2);           // "2014-15" -> "14-15"
  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") n.className = v; else if (k === "style") n.style.cssText = v; else n.setAttribute(k, v);
    }
    for (const k of kids) n.append(k instanceof Node ? k : document.createTextNode(String(k)));
    return n;
  };
  const strong = (t) => el("b", {}, t);
  const setTakeaway = (id, parts) => { const h = $(id); h.replaceChildren(...parts.map((p) => (p instanceof Node ? p : document.createTextNode(p)))); };
  const rows = (t) => t.rows.map((r) => Object.fromEntries(t.cols.map((c, i) => [c, r[i]])));
  const getJSON = (p) => fetch(p).then((r) => { if (!r.ok) throw new Error(p + " " + r.status); return r.json(); });

  // ------------------------------------------------------------------ state
  const S = {
    season: null, stype: "Regular Season", minMin: 1000, window: "3yr",
    sortKey: "xrapm", sortDir: -1, showAll: false, playerId: null, scMode: "diff",
  };
  const MIN_FGA = { "Regular Season": 300, Playoffs: 75 };
  const MIN_DEFAULT = { "Regular Season": [1000, 2500, 100], Playoffs: [150, 600, 25] };
  let META, SEASONS, POOLED, NAME_TO_ID = new Map(), ID_TO_NAME = new Map();
  const playerCache = new Map();

  // ------------------------------------------------------------------ boot
  Promise.all([getJSON("data/meta.json"), getJSON("data/seasons.json"), getJSON("data/pooled.json")])
    .then(([meta, seasons, pooled]) => {
      META = meta; SEASONS = rows(seasons); POOLED = rows(pooled);
      init();
    })
    .catch((e) => {
      console.error(e);
      $("main").prepend(el("p", { class: "note" }, "Couldn't load the data files. Try refreshing."));
    });

  function init() {
    // header stats
    const c = META.counts || {}, ev = (META.model || {}).evaluation || {};
    const setStat = (k, v) => { const n = $(`[data-k="${k}"]`); if (n && v != null) n.textContent = v; };
    setStat("shots", c.shots ? compact(c.shots) : null);
    setStat("seasons", c.seasons);
    setStat("stints", c.stints ? compact(c.stints) : null);
    setStat("ll", ev.log_loss_reduction_pct != null ? ev.log_loss_reduction_pct.toFixed(1) + "%" : null);
    if (c.shots) $$('[data-k="shots-full"]').forEach((n) => (n.textContent = compact(c.shots)));
    if (META.exported_at && META.exported_at !== "DEV") $("#exported").textContent = "Data exported " + META.exported_at.slice(0, 10);

    for (const r of SEASONS) { if (r.fga >= 100) { NAME_TO_ID.set(r.name, r.id); } ID_TO_NAME.set(r.id, r.name); }
    $("#p-names").replaceChildren(...[...NAME_TO_ID.keys()].sort().map((n) => el("option", { value: n })));

    const seasonList = [...new Set(SEASONS.map((r) => r.season))].sort().reverse();
    S.season = seasonList[0];
    $("#f-season").replaceChildren(...seasonList.map((s) => el("option", { value: s }, s)));

    bindControls();
    syncMinSlider();
    renderAll(true);

    let lastW = innerWidth;
    addEventListener("resize", debounce(() => { if (Math.abs(innerWidth - lastW) > 30) { lastW = innerWidth; renderCharts(); } }, 150));
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => renderCharts());
  }

  function bindControls() {
    $("#f-season").addEventListener("change", (e) => { S.season = e.target.value; renderAll(); });
    segment("#f-stype", (v) => { S.stype = v; syncMinSlider(true); renderAll(); });
    segment("#f-window", (v) => { S.window = v; renderLeaderboard(); });
    segment("#f-sc", (v) => { S.scMode = v; renderShotChart(); });
    const rng = $("#f-min");
    rng.addEventListener("input", () => { S.minMin = +rng.value; $("#f-min-out").textContent = fmtInt(S.minMin); });
    rng.addEventListener("change", () => renderAll());
    $$("#lb thead th[data-k] button").forEach((b) => b.addEventListener("click", () => {
      const k = b.parentElement.dataset.k;
      if (S.sortKey === k) S.sortDir *= -1; else { S.sortKey = k; S.sortDir = k === "name" || k === "team" ? 1 : -1; }
      renderLeaderboard();
    }));
    $("#lb-more").addEventListener("click", () => { S.showAll = !S.showAll; renderLeaderboard(); });
    const search = $("#p-search");
    const pick = () => { const id = NAME_TO_ID.get(search.value.trim()); if (id) selectPlayer(id, false); };
    search.addEventListener("change", pick);
    search.addEventListener("keydown", (e) => { if (e.key === "Enter") pick(); });
  }

  function segment(sel, onChange) {
    $$(sel + " button").forEach((b) => b.addEventListener("click", () => {
      if (b.disabled) return;
      $$(sel + " button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      onChange(b.dataset.v);
    }));
  }
  function setSegment(sel, v) { $$(sel + " button").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.v === v))); }

  function syncMinSlider(reset) {
    const [def, max, step] = MIN_DEFAULT[S.stype];
    const rng = $("#f-min");
    rng.max = max; rng.step = step;
    if (reset || S.minMin > max) S.minMin = def;
    rng.value = S.minMin; $("#f-min-out").textContent = fmtInt(S.minMin);
  }

  function renderAll(first) {
    renderLeaderboard(first);
    renderShotMaking();
    renderModel();
    if (first || S.playerId == null) {
      const top = [...leaderboardRows()].sort((a, b) => b.xrapm - a.xrapm)[0];
      if (top) selectPlayer(top.id, false, true); else renderProfile();
    } else renderProfile();
  }
  function renderCharts() { renderShotMaking(); renderShotChart(); renderTimeline(); renderModel(); }

  // ------------------------------------------------------------------ 1. leaderboard
  function windowLabel(season) {
    const y = +season.slice(0, 4);
    return `${y - 2}-${String(y - 1).slice(2)} → ${season}`;
  }
  function hasPooled(season, stype) { return POOLED.some((r) => r.season === season && r.stype === stype); }

  function leaderboardRows() {
    const pooledOK = hasPooled(S.season, S.stype);
    const btn3 = $('#f-window button[data-v="3yr"]');
    btn3.disabled = !pooledOK;
    btn3.title = pooledOK ? "Pooled over the selected season and the two before it: more stable" : "Needs three seasons of data";
    const win = pooledOK ? S.window : "1yr";
    setSegment("#f-window", win);
    let out;
    if (win === "3yr") {
      const teamOf = new Map(SEASONS.filter((r) => r.season === S.season && r.stype === S.stype).map((r) => [r.id, r.team]));
      out = POOLED.filter((r) => r.season === S.season && r.stype === S.stype && r.xrapm != null && (r.min || 0) / 3 >= S.minMin)
        .map((r) => ({ id: r.id, name: r.name || ID_TO_NAME.get(r.id) || "Unknown", team: teamOf.get(r.id) || r.team || "", xrapm: r.xrapm, rapm: r.rapm, min: r.min }));
    } else {
      out = SEASONS.filter((r) => r.season === S.season && r.stype === S.stype && r.xrapm != null && (r.min || 0) >= S.minMin)
        .map((r) => ({ id: r.id, name: r.name, team: r.team, xrapm: r.xrapm, rapm: r.rapm, min: r.min }));
    }
    out.forEach((r) => (r.luck = r.rapm != null ? r.rapm - r.xrapm : null));
    out._win = win;
    return out;
  }

  function renderLeaderboard() {
    const data = leaderboardRows(), win = data._win;
    const byX = [...data].sort((a, b) => b.xrapm - a.xrapm);
    const k = S.sortKey, dir = S.sortDir;
    const sorted = [...data].sort((a, b) => {
      const va = a[k], vb = b[k];
      if (va == null) return 1; if (vb == null) return -1;
      return (typeof va === "string" ? va.localeCompare(vb) : va - vb) * dir;
    });
    const shown = S.showAll ? sorted : sorted.slice(0, 25);
    const maxAbs = Math.max(1, ...data.map((r) => Math.abs(r.xrapm)));
    const rankOf = new Map(byX.map((r, i) => [r.id, i + 1]));
    const span = win === "3yr" ? windowLabel(S.season) : S.season;
    const st = S.stype === "Playoffs" ? " playoffs" : "";

    $$("#lb thead th[data-k]").forEach((th) => {
      if (th.dataset.k === k) th.setAttribute("aria-sort", dir < 0 ? "descending" : "ascending"); else th.removeAttribute("aria-sort");
    });
    $("#lb-title").textContent = `${win === "3yr" ? "3-season" : "Single-season"} xRAPM, ${span}${st} · ${data.length} players`;
    const tb = $("#lb tbody");
    tb.replaceChildren(...shown.map((r) => {
      const w = (Math.abs(r.xrapm) / maxAbs) * 50;
      const pos = r.xrapm >= 0;
      const bar = el("div", { class: "bar", "aria-hidden": "true" },
        el("span", { class: "zero" }), el("span", { class: "fill " + (pos ? "p" : "n"), style: `width:${w}%` }));
      const tr = el("tr", { tabindex: "0", "aria-label": `${r.name}, open profile` },
        el("td", { class: "rank" }, rankOf.get(r.id)),
        el("td", { class: "name" }, r.name),
        el("td", { class: "team hide-sm" }, r.team || ""),
        el("td", { class: "num xval" }, signed(r.xrapm)),
        el("td", { class: "barcell hide-sm" }, bar),
        el("td", { class: "num hide-sm" }, signed(r.rapm)),
        el("td", { class: "num luck" }, signed(r.luck)),
        el("td", { class: "num hide-sm" }, fmtInt(r.min)));
      const go = () => selectPlayer(r.id, true);
      tr.addEventListener("click", go);
      tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
      return tr;
    }));
    $("#lb-more").hidden = data.length <= 25;
    $("#lb-more").textContent = S.showAll ? "Show top 25" : `Show all ${data.length}`;

    const top = byX[0];
    if (!top) { setTakeaway("#t-impact", ["No players match these filters. Try lowering the minutes."]); return; }
    const second = byX[1];
    setTakeaway("#t-impact", [
      strong(top.name), ` has the biggest expected impact${win === "3yr" ? " over " + span : " in " + S.season}${st}: `,
      strong(signed(top.xrapm) + " points per 100 possessions"), " versus an average player",
      second ? `, ahead of ${second.name} (${signed(second.xrapm)}).` : ".",
    ]);
  }

  // ------------------------------------------------------------------ 2. shot-making scatter
  function shotMakingRows() {
    return SEASONS.filter((r) => r.season === S.season && r.stype === S.stype && r.fga >= MIN_FGA[S.stype] && (r.min || 0) >= S.minMin && r.fg != null && r.xfg != null)
      .map((r) => ({ ...r, x: r.xfg * 100, y: (r.fg - r.xfg) * 100 }));
  }

  function renderShotMaking() {
    const data = shotMakingRows();
    const host = $("#sm-chart");
    const lists = $("#sm-lists");
    if (!data.length) { host.replaceChildren(el("p", { class: "note" }, "No players match these filters.")); lists.replaceChildren(); setTakeaway("#t-sm", ["No players match these filters."]); return; }
    const byY = [...data].sort((a, b) => b.y - a.y);
    const over = byY.slice(0, 5), under = byY.slice(-5).reverse();
    const hot = new Set(over.map((d) => d.id)), cold = new Set(under.map((d) => d.id));
    const POS = css("--pos"), NEG = css("--neg"), DOT = css("--dot"), SURF = css("--surface"), AXIS = css("--axis");
    const width = Math.max(300, host.clientWidth || 600);
    const nLab = width < 480 ? 2 : 3;
    const labelled = new Set([...over.slice(0, nLab), ...under.slice(0, nLab)].map((d) => d.id));
    const lastName = (n) => { const p = n.split(" "); return p.length > 1 ? p.slice(1).join(" ") : n; };
    const tipTitle = (d) => `${d.name} (${d.team})\nFG% ${pct(d.fg)} vs expected ${pct(d.xfg)}\n${signed(d.y)} pts · ${fmtInt(d.fga)} shots`;
    const color = (d) => (hot.has(d.id) ? POS : cold.has(d.id) ? NEG : DOT);
    const fig = Plot.plot({
      width, height: Math.round(Math.min(440, Math.max(300, width * 0.62))),
      marginLeft: 46, marginBottom: 42, marginRight: 16, marginTop: 26,
      style: { background: "transparent", fontSize: "12px", color: css("--ink-2") },
      x: { label: "Shot difficulty: expected FG% of his shots →  (right = easier shots)", labelAnchor: "center", labelOffset: 36, tickFormat: (d) => d + "%", nice: true },
      y: { label: "↑ FG% above expected (pts)", labelAnchor: "top", tickFormat: (d) => (d > 0 ? "+" : d < 0 ? MINUS : "") + Math.abs(d), nice: true, grid: true },
      marks: [
        Plot.ruleY([0], { stroke: AXIS }),
        Plot.dot(data.filter((d) => !hot.has(d.id) && !cold.has(d.id)), { x: "x", y: "y", r: 4, fill: DOT, stroke: SURF, strokeWidth: 1.5 }),
        Plot.dot(data.filter((d) => hot.has(d.id) || cold.has(d.id)), { x: "x", y: "y", r: 5, fill: color, stroke: SURF, strokeWidth: 2 }),
        Plot.text(data.filter((d) => labelled.has(d.id)), { x: "x", y: "y", text: (d) => lastName(d.name), dy: -11, fontSize: 11.5, fontWeight: 600, fill: css("--ink"), stroke: SURF, strokeWidth: 3, paintOrder: "stroke" }),
        Plot.tip(data, Plot.pointer({ x: "x", y: "y", title: tipTitle, maxRadius: 30, fill: SURF, stroke: AXIS })),
      ],
    });
    styleAxes(fig);
    fig.addEventListener("click", () => { const d = fig.value; if (d) selectPlayer(d.id, true); });
    fig.style.cursor = "pointer";
    host.replaceChildren(fig);

    const li = (d, c) => {
      const n = el("li", { tabindex: "0", role: "button" },
        el("span", {}, el("span", { class: "k", style: `background:${c}` }), d.name),
        el("b", {}, signed(d.y)));
      n.addEventListener("click", () => selectPlayer(d.id, true));
      n.addEventListener("keydown", (e) => { if (e.key === "Enter") selectPlayer(d.id, true); });
      return n;
    };
    lists.replaceChildren(
      el("div", {}, el("h4", {}, "Best shot-makers"), el("ol", {}, ...over.map((d) => li(d, POS)))),
      el("div", {}, el("h4", {}, "Most below expected"), el("ol", {}, ...under.map((d) => li(d, NEG)))),
    );
    $("#sm-title").textContent = `FG% vs. expected, ${S.season}${S.stype === "Playoffs" ? " playoffs" : ""} · ${data.length} players`;
    $("#sm-note").textContent = `Players with ${MIN_FGA[S.stype]}+ shot attempts and ${fmtInt(S.minMin)}+ minutes. Values are percentage points of FG%. Click a dot to open the profile.`;
    const b = over[0];
    setTakeaway("#t-sm", [
      strong(b.name), " made ", strong(`${b.y.toFixed(1)} percentage points more`), ` of his shots than their difficulty predicts (${pct(b.fg)} on shots worth ${pct(b.xfg)}), the best mark among ${data.length} qualified players.`,
    ]);
  }

  // ------------------------------------------------------------------ 3. profile
  function selectPlayer(id, scroll, quiet) {
    S.playerId = id;
    $("#p-search").value = ID_TO_NAME.get(id) || "";
    renderProfile();
    if (scroll && !quiet) $("#profile").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  }

  function loadPlayer(id) {
    if (!playerCache.has(id)) playerCache.set(id, getJSON(`data/players/${id}.json`).catch(() => null));
    return playerCache.get(id);
  }

  let profileToken = 0;
  function renderProfile() {
    const id = S.playerId; if (id == null) return;
    const tok = ++profileToken;
    $("#sc-chart").classList.add("loading");
    renderTimeline();
    loadPlayer(id).then((p) => { if (tok !== profileToken) return; S._player = p; $("#sc-chart").classList.remove("loading"); renderShotChart(); });
  }

  function playerSeason(id, season, stype) { return SEASONS.find((r) => r.id === id && r.season === season && r.stype === stype); }

  function pickChartSeason(p) {
    const charts = (p && p.charts) || {};
    if (charts[S.stype] && charts[S.stype][S.season]) return [S.stype, S.season];
    const order = [S.stype, S.stype === "Playoffs" ? "Regular Season" : "Playoffs"];
    for (const t of order) {
      const ss = Object.keys(charts[t] || {}).sort();
      if (ss.length) {
        // nearest earlier season, else latest
        const earlier = ss.filter((s) => s <= S.season);
        return [t, earlier.length ? earlier[earlier.length - 1] : ss[ss.length - 1]];
      }
    }
    return null;
  }

  function renderShotChart() {
    const host = $("#sc-chart"), p = S._player, id = S.playerId;
    const name = ID_TO_NAME.get(id) || "";
    const pick = pickChartSeason(p);
    if (!p || !pick) {
      host.replaceChildren(el("p", { class: "note" }, "No shot chart available for this player."));
      $("#sc-legend").replaceChildren(); $("#p-stats").replaceChildren();
      setTakeaway("#t-p", [strong(name), " doesn't have enough shots for a shot chart. Try another player."]);
      return;
    }
    const [stype, season] = pick;
    const bins = p.charts[stype][season];
    const B = (p.bin_ft || 2) * 10;
    const R = 32; // hexagon circumradius in court units (tenths of a foot)
    const hexes = new Map();
    for (const [bx, by, att, made, xs] of bins) {
      const x = bx * B + B / 2, y = by * B + B / 2;
      // pointy-top axial coords
      const q = ((Math.sqrt(3) / 3) * x - (1 / 3) * y) / R, r = ((2 / 3) * y) / R;
      let rx = Math.round(q), rz = Math.round(r), ry = Math.round(-q - r);
      const dx = Math.abs(rx - q), dz = Math.abs(rz - r), dy = Math.abs(ry - (-q - r));
      if (dx > dy && dx > dz) rx = -ry - rz; else if (dz > dy) rz = -rx - ry;
      const key = rx + "," + rz;
      const h = hexes.get(key) || { cx: R * Math.sqrt(3) * (rx + rz / 2), cy: R * 1.5 * rz, att: 0, made: 0, xs: 0 };
      h.att += att; h.made += made; h.xs += xs; hexes.set(key, h);
    }
    const Y0 = -52.5, Y1 = 300, X0 = -250, X1 = 250;
    let data = [...hexes.values()].filter((h) => h.cy >= Y0 && h.cy <= Y1 && h.cx >= X0 && h.cx <= X1);
    const maxAtt = Math.max(...data.map((h) => h.att));
    const width = Math.max(280, Math.min(600, host.clientWidth || 520));
    const k = width / (X1 - X0);
    const height = Math.round((Y1 - Y0) * k);
    data.forEach((h) => {
      h.fg = h.made / h.att; h.xfg = h.xs / h.att;
      h.diff = (h.made - h.xs) / (h.att + 6);          // shrunk toward expected for small samples
      h.rpx = Math.max(1.6, R * k * 0.94 * Math.sqrt(Math.min(1, h.att / (maxAtt * 0.35))));
      h.ft = Math.hypot(h.cx, h.cy) / 10;
    });
    const HEX = { draw(ctx, size) { const rr = Math.sqrt(size / Math.PI); for (let i = 0; i < 6; i++) { const a = -Math.PI / 2 + (i * Math.PI) / 3; i ? ctx.lineTo(rr * Math.cos(a), rr * Math.sin(a)) : ctx.moveTo(rr * Math.cos(a), rr * Math.sin(a)); } ctx.closePath(); } };
    const POS = css("--pos"), NEG = css("--neg"), MID = css("--mid"), AXIS = css("--axis"), SURF = css("--surface");
    const color = S.scMode === "diff"
      ? { type: "linear", domain: [-0.15, 0, 0.15], range: [NEG, MID, POS], clamp: true, interpolate: "lab" }
      : { type: "linear", domain: [0.3, 0.7], range: [css("--chip") === "#262624" ? "#184f95" : "#cde2fb", css("--chip") === "#262624" ? "#9ec5f4" : "#104281"], clamp: true, interpolate: "lab" };
    const fillOf = (h) => (S.scMode === "diff" ? h.diff : h.xfg);
    const fig = Plot.plot({
      width, height, margin: 0,
      x: { domain: [X0, X1], axis: null }, y: { domain: [Y0, Y1], axis: null },
      r: { type: "identity" }, color,
      style: { background: "transparent", fontSize: "12px" },
      marks: [
        ...courtMarks(AXIS),
        Plot.dot(data, { x: "cx", y: "cy", r: "rpx", symbol: HEX, fill: fillOf, stroke: null,
          title: (h) => `${h.ft.toFixed(0)} ft from the rim\n${h.made} of ${h.att} made (${pct(h.fg, 0)})\nExpected ${pct(h.xfg, 0)} · ${signed((h.fg - h.xfg) * 100, 0)} pts`,
          tip: { fill: SURF, stroke: AXIS } }),
      ],
    });
    host.replaceChildren(fig);

    // legend
    const lg = $("#sc-legend");
    if (S.scMode === "diff") {
      lg.replaceChildren(el("span", {}, "Colder"), el("span", { class: "ramp", style: `background:linear-gradient(90deg, ${NEG}, ${MID}, ${POS})` }), el("span", {}, "Hotter than expected"), el("span", {}, "· Bigger hexagon = more shots"));
    } else {
      lg.replaceChildren(el("span", {}, "Harder (30%)"), el("span", { class: "ramp", style: `background:linear-gradient(90deg, ${color.range[0]}, ${color.range[1]})` }), el("span", {}, "Easier (70%+) expected FG%"), el("span", {}, "· Bigger hexagon = more shots"));
    }
    const fallback = season !== S.season || stype !== S.stype;
    $("#sc-title").textContent = `Shot chart, ${season}${stype === "Playoffs" ? " playoffs" : ""}${fallback ? " (latest available)" : ""}`;

    // stats + takeaway
    const row = playerSeason(id, season, stype);
    const tot = data.reduce((a, h) => ({ att: a.att + h.att, made: a.made + h.made, xs: a.xs + h.xs }), { att: 0, made: 0, xs: 0 });
    const fg = row && row.fg != null ? row.fg : tot.made / tot.att, xfg = row && row.xfg != null ? row.xfg : tot.xs / tot.att;
    const diff = (fg - xfg) * 100;
    const ps = $("#p-stats");
    ps.replaceChildren(
      ...[["Team", row ? row.team : "–"], ["FGA", fmtInt(row ? row.fga : tot.att)], ["FG%", pct(fg)], ["Expected", pct(xfg)],
        ["vs. exp.", signed(diff) + " pts"], ["xRAPM", row ? signed(row.xrapm) : "–"]]
        .map(([k2, v]) => el("span", {}, k2 + " ", strong(v))));
    const verb = diff >= 0.5 ? "above" : diff <= -0.5 ? "below" : "right at";
    setTakeaway("#t-p", [
      strong(name), ` shot ${pct(fg)} in ${season}${stype === "Playoffs" ? " playoffs" : ""} on shots an average player makes ${pct(xfg)} of the time: `,
      strong(verb === "right at" ? "right at expectation" : `${Math.abs(diff).toFixed(1)} points ${verb} expected`), ".",
    ]);
  }

  function courtMarks(stroke) {
    const arc = (cx, cy, r, a0, a1, n = 48) => d3.range(n + 1).map((i) => { const a = a0 + ((a1 - a0) * i) / n; return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; });
    const t = Math.acos(220 / 237.5);
    const lines = [
      [[-250, -47.5], [250, -47.5]],                                   // baseline
      [[-250, -47.5], [-250, 300]], [[250, -47.5], [250, 300]],        // sidelines
      [[-80, -47.5], [-80, 142.5], [80, 142.5], [80, -47.5]],          // paint
      [[-60, -47.5], [-60, 142.5]], [[60, -47.5], [60, 142.5]],
      [[-30, -7.5], [30, -7.5]],                                       // backboard
      [[-220, -47.5], [-220, 92.5]], [[220, -47.5], [220, 92.5]],      // corner threes
      arc(0, 0, 237.5, t, Math.PI - t, 80),                            // arc
      arc(0, 142.5, 60, 0, Math.PI),                                   // FT circle
      arc(0, 0, 40, 0, Math.PI),                                       // restricted area
      arc(0, 0, 7.5, 0, 2 * Math.PI, 24),                              // rim
    ];
    return lines.map((pts) => Plot.line(pts, { x: (d) => d[0], y: (d) => d[1], stroke, strokeWidth: 1, curve: "linear" }));
  }

  function renderTimeline() {
    const host = $("#tl-chart"), id = S.playerId;
    const name = ID_TO_NAME.get(id) || "";
    const data = SEASONS.filter((r) => r.id === id && r.stype === S.stype && r.xrapm != null && (r.min || 0) >= (S.stype === "Playoffs" ? 50 : 300))
      .sort((a, b) => a.season.localeCompare(b.season));
    $("#tl-title").textContent = `${name}: impact by season${S.stype === "Playoffs" ? " (playoffs)" : ""}`;
    if (data.length === 0) { host.replaceChildren(el("p", { class: "note" }, "No rated seasons for this selection.")); return; }
    const S1 = css("--s1"), S2 = css("--s2"), SURF = css("--surface"), AXIS = css("--axis");
    const width = Math.max(280, host.clientWidth || 480);
    const long = data.flatMap((d) => [{ season: d.season, k: "xRAPM", v: d.xrapm }, { season: d.season, k: "RAPM", v: d.rapm }]).filter((d) => d.v != null);
    const last = data[data.length - 1];
    const ends = [{ season: last.season, k: "xRAPM", v: last.xrapm }, { season: last.season, k: "RAPM", v: last.rapm }].filter((d) => d.v != null);
    if (ends.length === 2 && Math.abs(ends[0].v - ends[1].v) < 0.5) { const up = ends[0].v >= ends[1].v ? 0 : 1; ends[up].dy = -8; ends[1 - up].dy = 8; }
    const fig = Plot.plot({
      width, height: Math.round(Math.min(340, Math.max(240, width * 0.62))),
      marginLeft: 40, marginRight: 52, marginBottom: 34, marginTop: 26,
      style: { background: "transparent", fontSize: "12px", color: css("--ink-2") },
      x: { type: "point", label: null, tickFormat: shortSeason, padding: 0.3, domain: data.map((d) => d.season) },
      y: { label: "↑ Points per 100 possessions", labelAnchor: "top", grid: true, nice: true, tickFormat: (d) => (d > 0 ? "+" : d < 0 ? MINUS : "") + Math.abs(d) },
      color: { domain: ["xRAPM", "RAPM"], range: [S1, S2] },
      marks: [
        Plot.ruleY([0], { stroke: AXIS }),
        Plot.ruleX([S.season], { stroke: css("--grid"), strokeWidth: 10, strokeOpacity: 0.9 }),
        Plot.line(long, { x: "season", y: "v", stroke: "k", strokeWidth: 2, curve: "monotone-x" }),
        Plot.dot(long, { x: "season", y: "v", fill: "k", r: 4, stroke: SURF, strokeWidth: 2 }),
        ...ends.map((e) => Plot.text([e], { x: "season", y: "v", text: "k", dx: 9, dy: e.dy || 0, textAnchor: "start", fontSize: 11.5, fontWeight: 600, fill: css("--ink-2") })),
        Plot.tip(data, Plot.pointerX({ x: "season", y: "xrapm", title: (d) => `${d.season} · ${d.team}\nxRAPM ${signed(d.xrapm)}\nRAPM ${signed(d.rapm)}\n${fmtInt(d.min)} minutes`, fill: SURF, stroke: AXIS })),
      ],
    });
    styleAxes(fig);
    host.replaceChildren(fig);
  }

  // ------------------------------------------------------------------ 4. model
  function renderModel() {
    const cal = META.calibration, ev = (META.model || {}).evaluation || {};
    const host = $("#cal-chart");
    if (cal && cal.mean_predicted) {
      const pts = cal.mean_predicted.map((p, i) => ({ p, a: cal.fraction_positive[i] }));
      const mae = d3.mean(pts, (d) => Math.abs(d.p - d.a)) * 100;
      const width = Math.max(260, Math.min(340, host.clientWidth || 320));
      const S1 = css("--s1"), SURF = css("--surface"), AXIS = css("--axis");
      const fig = Plot.plot({
        width, height: width, marginLeft: 44, marginBottom: 40, marginTop: 24, marginRight: 12,
        style: { background: "transparent", fontSize: "12px", color: css("--ink-2") },
        x: { domain: [0, 1], label: "Predicted chance of a make →", labelAnchor: "center", labelOffset: 34, tickFormat: (d) => d * 100 + "%", ticks: 5 },
        y: { domain: [0, 1], label: "↑ Actual make rate", labelAnchor: "top", tickFormat: (d) => d * 100 + "%", ticks: 5, grid: true },
        marks: [
          Plot.line([[0, 0], [1, 1]], { stroke: AXIS, strokeWidth: 1 }),
          Plot.text([[0.62, 0.53]], { text: ["perfect calibration"], rotate: -45, fill: css("--muted"), fontSize: 11 }),
          Plot.line(pts, { x: "p", y: "a", stroke: S1, strokeWidth: 2 }),
          Plot.dot(pts, { x: "p", y: "a", r: 4, fill: S1, stroke: SURF, strokeWidth: 2 }),
          Plot.tip(pts, Plot.pointer({ x: "p", y: "a", title: (d) => `Predicted ${pct(d.p, 0)}\nActual ${pct(d.a, 0)}`, fill: SURF, stroke: AXIS })),
        ],
      });
      styleAxes(fig);
      host.replaceChildren(fig);
      setTakeaway("#t-m", [
        "When xShot says a shot goes in 40% of the time, it goes in about 40% of the time. Across 20 probability bins its predictions are off by ",
        strong(`${mae.toFixed(1)} points on average`), ".",
      ]);
    }
    const tile = (v, label) => el("div", { class: "tile" }, el("b", {}, v), el("span", {}, label));
    const m = META.model || {};
    $("#tiles").replaceChildren(
      tile(ev.log_loss_reduction_pct != null ? ev.log_loss_reduction_pct.toFixed(1) + "%" : "–", "lower log loss than predicting league-average FG%"),
      tile(ev.brier_score != null ? ev.brier_score.toFixed(3) : "–", "Brier score (≈0.249 for a league-average guess; lower is better)"),
      tile(ev.test_n_shots ? compact(ev.test_n_shots) : "–", "held-out shots the model never trained on"),
      el("p", { class: "tile-note" },
        `XGBoost, ${m.feature_count || 30} pre-shot features (location, shot type, clock). Trained on ${m.train_seasons || "2014-15 → 2022-23"}, tested on ${m.test_seasons || "2023-24 → 2024-25"}. `,
        "The model never sees who is shooting, so it measures shot difficulty, not shooter skill."),
    );
  }

  // ------------------------------------------------------------------ helpers
  function styleAxes(fig) {
    const AXIS = css("--axis"), GRID = css("--grid");
    fig.querySelectorAll('[aria-label$="tick"] path, [aria-label$="tick"] line').forEach((n) => n.setAttribute("stroke", AXIS));
    fig.querySelectorAll('[aria-label$="grid"] line, [aria-label$="grid"] path').forEach((n) => { n.setAttribute("stroke", GRID); n.setAttribute("stroke-opacity", "1"); });
  }
  function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
})();
