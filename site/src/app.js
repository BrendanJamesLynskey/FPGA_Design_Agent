/* FPGA Design Agent site. No dependencies. Every animation is frame(step) over a state list built from site/data/*.json. */
(function () {
  "use strict";
  var D = {};
  document.querySelectorAll('script[type="application/json"][data-key]').forEach(function (s) {
    try { D[s.dataset.key] = JSON.parse(s.textContent); } catch (e) { /* data missing: component skips */ }
  });
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var NS = "http://www.w3.org/2000/svg";
  function el(tag, attrs, kids) {
    var e = document.createElement(tag);
    for (var k in (attrs || {})) { if (k === "text") e.textContent = attrs[k]; else e.setAttribute(k, attrs[k]); }
    (kids || []).forEach(function (c) { e.appendChild(c); });
    return e;
  }
  function sv(tag, attrs, text) {
    var e = document.createElementNS(NS, tag);
    for (var k in (attrs || {})) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    return e;
  }

  /* theme toggle: remembered per viewer, optional */
  var tb = document.getElementById("theme");
  function curTheme() {
    var t = document.documentElement.dataset.theme;
    if (t) return t;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  if (tb) {
    try { var st = localStorage.getItem("fda-theme"); if (st) document.documentElement.dataset.theme = st; } catch (e) {}
    tb.addEventListener("click", function () {
      var n = curTheme() === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = n;
      try { localStorage.setItem("fda-theme", n); } catch (e) {}
      tb.textContent = n === "dark" ? "Light" : "Dark"; tb.setAttribute("aria-label", "Switch to " + tb.textContent.toLowerCase() + " theme");
    });
    tb.textContent = curTheme() === "dark" ? "Light" : "Dark"; tb.setAttribute("aria-label", "Switch to " + tb.textContent.toLowerCase() + " theme");
  }

  /* generic player: n steps, play/pause, step, scrub, speed, reset; keyboard when focused; pauses off-screen */
  function Player(root, n, onFrame, opts) {
    opts = opts || {};
    var i = 0, playing = false, timer = null, speed = 1, visible = true, base = opts.interval || 1100;
    var live = root.querySelector(".cap");
    var play = el("button", { type: "button", "aria-label": "Play", text: "Play" });
    var back = el("button", { type: "button", "aria-label": "Step back", text: "Back" });
    var fwd = el("button", { type: "button", "aria-label": "Next step", text: "Next" });
    var rst = el("button", { type: "button", "aria-label": "Reset", text: "Reset" });
    var rng = el("input", { type: "range", min: 0, max: n - 1, value: 0, step: 1, "aria-label": "Step" });
    var pos = el("span", { class: "pos" });
    var sp = el("select", { "aria-label": "Speed" });
    [0.25, 0.5, 1, 2, 4].forEach(function (s) { var o = el("option", { value: s, text: s + "x" }); if (s === 1) o.selected = true; sp.appendChild(o); });
    var ctl = el("div", { class: "ctl" }, [play, back, fwd, rst, rng, pos, sp]);
    root.appendChild(ctl);
    if (!root.hasAttribute("tabindex")) root.setAttribute("tabindex", "0");
    function show() {
      rng.value = i; pos.textContent = (i + 1) + " / " + n;
      var c = onFrame(i);
      if (live && c != null) live.textContent = c;
    }
    function stop() { playing = false; play.textContent = "Play"; play.setAttribute("aria-label", "Play"); clearTimeout(timer); }
    function tick() {
      if (!playing) return;
      if (!visible) { timer = setTimeout(tick, 400); return; }
      if (i >= n - 1) { stop(); return; }
      i++; show(); timer = setTimeout(tick, base / speed);
    }
    function go() {
      if (i >= n - 1) i = 0;
      playing = true; play.textContent = "Pause"; play.setAttribute("aria-label", "Pause"); show(); timer = setTimeout(tick, base / speed);
    }
    play.onclick = function () { playing ? stop() : go(); };
    back.onclick = function () { stop(); i = Math.max(0, i - 1); show(); };
    fwd.onclick = function () { stop(); i = Math.min(n - 1, i + 1); show(); };
    rst.onclick = function () { stop(); i = 0; show(); };
    rng.oninput = function () { stop(); i = +rng.value; show(); };
    sp.onchange = function () { speed = +sp.value; };
    root.addEventListener("keydown", function (e) {
      if (e.target !== root) return;
      if (e.key === " ") { e.preventDefault(); play.onclick(); }
      else if (e.key === "ArrowRight") { e.preventDefault(); fwd.onclick(); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); back.onclick(); }
      else if (e.key === "Home") { e.preventDefault(); rst.onclick(); }
    });
    if ("IntersectionObserver" in window) new IntersectionObserver(function (es) { visible = es[0].isIntersecting; }).observe(root);
    show();
    if (opts.autoplay && !reduce) go();
    return { goto: function (k) { stop(); i = k; show(); } };
  }

  /* ---------- stage replay (hero and how-it-works): frames from the committed run record ---------- */
  var GROUPS = [
    { id: "clarify", label: "Interview", stages: [0] },
    { id: "plan", label: "Plan", stages: [1] },
    { id: "rtl", label: "RTL and gates V0 to V3", stages: [2] },
    { id: "build", label: "Build", stages: [3, 4, 5] },
    { id: "post", label: "Post-route gates", stages: [6, 7, 8] },
    { id: "board", label: "Board", stages: [9] }
  ];
  var DETAIL = [
    "Interview", "Plan", "RTL and V0 to V3", "Constraints", "Synthesis", "Implementation", "Timing closure",
    "Power closure", "DRC closure", "Board and debug"
  ];
  function frameState(R, i) {
    var s = R.steps[i];
    return { stage: s.stage_no, step: s, last: i === R.steps.length - 1 };
  }
  function mountReplay(root, mode) {
    var R = D.replay; if (!R) return;
    var items = mode === "hero" ? GROUPS : DETAIL.map(function (l, k) { return { id: "s" + k, label: l, stages: [k] }; });
    var ul = el("ul", { class: "pipe", "aria-label": "Stages" });
    var lis = items.map(function (g, k) {
      var li = el("li", {}, [el("b", { text: mode === "hero" ? String(k + 1) : String(g.stages[0]) }), document.createTextNode(g.label)]);
      ul.appendChild(li); return li;
    });
    var cap = el("p", { class: "cap", "aria-live": "polite" });
    root.appendChild(ul); root.appendChild(cap);
    function frame(i) {
      var st = frameState(R, i), cur = -1;
      items.forEach(function (g, k) { if (g.stages.indexOf(st.stage) >= 0) cur = k; });
      lis.forEach(function (li, k) {
        li.className = k < cur ? "done" : (k === cur ? (st.last ? "stop" : "active") : "");
        var old = li.querySelector(".v"); if (old) li.removeChild(old);
      });
      var visits = st.step.visits;
      if (visits > 1) lis[cur].appendChild(el("span", { class: "v", text: st.step.visit + "/" + visits }));
      return "Stage " + st.stage + ", " + DETAIL[st.stage] + (visits > 1 ? " (visit " + st.step.visit + " of " + visits + ")" : "") + ". " + st.step.fact;
    }
    Player(root, R.steps.length, frame, { autoplay: mode === "hero", interval: mode === "hero" ? 1300 : 1500 });
  }

  /* ---------- k-of-n strip, intervals, bars (shared by development data and eval1.json) ---------- */
  function strip(root, rows) {
    var g = el("div", { class: "strip", role: "list" });
    rows.forEach(function (r) {
      var dots = el("span", { class: "dots", "aria-hidden": "true" });
      for (var j = 0; j < r.n; j++) dots.appendChild(el("span", { class: "dot " + (j < r.k ? "p" : "f") }));
      for (var q = r.n; q < (r.of || r.n); q++) dots.appendChild(el("span", { class: "dot n", title: "not run" }));
      g.appendChild(el("span", { class: "t", role: "listitem", text: r.task }));
      g.appendChild(dots);
      g.appendChild(el("span", { class: "k mono", text: r.k + " of " + r.n }));
    });
    root.appendChild(g);
    root.appendChild(el("div", { class: "legend" }, [
      el("span", { text: "filled: all hidden tests passed" }), el("span", { text: "hatched: failed" }), el("span", { text: "dotted: not run" })]));
  }
  function intervals(root, items) {
    var W = 560, H = 36 + items.length * 52, L = 14, R = 14;
    var s = sv("svg", { viewBox: "0 0 " + W + " " + H, width: "100%", role: "img", "aria-label": items.map(function (x) { return x.label + " " + x.mid + " percent, interval " + x.lo + " to " + x.hi; }).join("; ") });
    function X(v) { return L + (W - L - R) * v / 100; }
    [0, 25, 50, 75, 100].forEach(function (v) {
      s.appendChild(sv("line", { x1: X(v), x2: X(v), y1: 6, y2: H - 20, class: "rule" }));
      s.appendChild(sv("text", { x: X(v), y: H - 6, "text-anchor": "middle" }, v));
    });
    items.forEach(function (it, k) {
      var y = 36 + k * 52;
      s.appendChild(sv("text", { x: 0, y: y - 14 }, it.label));
      s.appendChild(sv("line", { x1: X(it.lo), x2: X(it.hi), y1: y, y2: y, class: "ink", "stroke-width": 2, "stroke-dasharray": it.dash ? "5 3" : "none" }));
      s.appendChild(sv("line", { x1: X(it.lo), x2: X(it.lo), y1: y - 6, y2: y + 6, class: "ink", "stroke-width": 2 }));
      s.appendChild(sv("line", { x1: X(it.hi), x2: X(it.hi), y1: y - 6, y2: y + 6, class: "ink", "stroke-width": 2 }));
      s.appendChild(sv("circle", { cx: X(it.mid), cy: y, r: 5, class: "fillink" }));
    });
    root.appendChild(s);
    var t = el("div", { class: "tablewrap" });
    var tb2 = el("table");
    tb2.appendChild(el("tr", {}, ["Estimate", "Point", "95% interval"].map(function (h) { return el("th", { text: h }); })));
    items.forEach(function (it) {
      tb2.appendChild(el("tr", {}, [el("td", { text: it.label }), el("td", { class: "num", text: it.mid + "%" }), el("td", { class: "num", text: it.lo + " to " + it.hi + "%" })]));
    });
    t.appendChild(tb2); root.appendChild(t);
  }
  function bars(root, obj, total, unit) {
    var g = el("div", { class: "bars" });
    var max = Math.max.apply(null, Object.keys(obj).map(function (k) { return obj[k]; }).concat([1]));
    Object.keys(obj).forEach(function (k) {
      var b = el("span", { class: "b", "aria-hidden": "true" }); b.style.width = (100 * obj[k] / max) + "%"; b.style.display = "block";
      g.appendChild(el("span", { text: k.replace(/_/g, " ").replace(/-/g, " ") }));
      var cell = el("span", {}, [b]); g.appendChild(cell);
      g.appendChild(el("span", { class: "mono", text: obj[k] + (total ? " of " + total : "") + (unit || "") }));
    });
    root.appendChild(g);
  }
  var OUTCOME_TEXT = { pass: "passed, no repair needed", caught_and_repaired: "an internal gate failed, the agent repaired it, hidden tests passed",
    escape: "own checks passed, hidden tests failed (escape)", internal_stop_hidden_pass: "stopped on an internal gate, hidden tests pass on the RTL it left",
    fail: "failed" };

  function mountDev() {
    var d = D.dev; if (!d) return;
    var a = document.getElementById("dev-strip"); if (a) strip(a, d.per_task);
    var b = document.getElementById("dev-int");
    if (b) intervals(b, [
      { label: "pass@1, bootstrap over tasks", mid: d.pass_at_1_tasks_pct, lo: d.bootstrap_tasks_pct[0], hi: d.bootstrap_tasks_pct[1] },
      { label: "Wilson on runs (ignores tasks)", mid: d.pass_pct_runs, lo: d.wilson_runs_pct[0], hi: d.wilson_runs_pct[1], dash: true }]);
    var c = document.getElementById("dev-out"); if (c) {
      var o = {}; Object.keys(d.outcomes).forEach(function (k) { o[OUTCOME_TEXT[k] || k] = d.outcomes[k]; });
      bars(c, o, d.runs);
    }
    var e = document.getElementById("dev-esc"); if (e) bars(e, d.escape_levels, d.escapes);
  }
  function mountEval1() {
    var root = document.getElementById("eval1"); if (!root) return;
    var E = D.eval1;
    if (!E) {
      root.appendChild(el("div", { class: "stub" }, [
        el("span", { class: "tag run", text: "Stopped" }),
        el("p", { text: "No held-out score. eval-1 was stopped before any result was analysed; the baseline evaluation on the larger benchmark will be shown here when it is scored." })]));
      return;
    }
    root.appendChild(el("h3", { text: "Per task, hidden tests passed in k of 3 runs" }));
    var s = el("div"); root.appendChild(s); strip(s, E.per_task.map(function (t) { return { task: t.task, k: t.k, n: t.n, of: 3 }; }));
    root.appendChild(el("h3", { text: "pass@1 with 95% intervals" }));
    var i = el("div"); root.appendChild(i);
    intervals(i, [
      { label: "pass@1, bootstrap over tasks", mid: E.pass_at_1_pct, lo: E.bootstrap_pct[0], hi: E.bootstrap_pct[1] },
      { label: "Wilson on runs (ignores tasks)", mid: E.wilson_mid_pct, lo: E.wilson_pct[0], hi: E.wilson_pct[1], dash: true }]);
    root.appendChild(el("h3", { text: "Escapes by the check level that should have caught them" }));
    var b = el("div"); root.appendChild(b); bars(b, E.escape_levels, E.escapes);
  }

  /* ---------- ILA capture player (T1 on the board): LED0 against the sample index ---------- */
  function mountILA(root) {
    var B = D.board; if (!B) return;
    var keys = Object.keys(B.captures).sort(function (a, b) { return B.captures[a].duty - B.captures[b].duty; });
    var W = 600, H = 120, L = 30, cur = keys[0], svg, cursor, trace, label;
    var sel = el("div", { class: "ctl", role: "group", "aria-label": "Dimmer level" });
    var btns = keys.map(function (k) {
      var b = el("button", { type: "button", "aria-pressed": k === cur ? "true" : "false", text: "duty " + B.captures[k].duty });
      b.onclick = function () { cur = k; btns.forEach(function (x, j) { x.setAttribute("aria-pressed", keys[j] === cur ? "true" : "false"); }); draw(); player.goto(0); };
      return b;
    });
    btns.forEach(function (b) { sel.appendChild(b); });
    root.appendChild(sel);
    var holder = el("div"); root.appendChild(holder);
    root.appendChild(el("p", { class: "cap", "aria-live": "polite" }));
    function X(i) { return L + (W - L - 10) * i / (B.captures[cur].samples - 1); }
    function draw() {
      var c = B.captures[cur]; holder.innerHTML = "";
      svg = sv("svg", { viewBox: "0 0 " + W + " " + H, width: "100%", role: "img", "aria-label": "ILA capture of LED 0 over " + c.samples + " samples at duty " + c.duty + ": on for " + c.on + " samples" });
      svg.appendChild(sv("text", { x: 0, y: 34 }, "on"));
      svg.appendChild(sv("text", { x: 0, y: 94 }, "off"));
      var d = "", prev = 0;
      c.edges.forEach(function (e, k) {
        var y = e[1] ? 30 : 90;
        d += (k === 0 ? "M" : "L") + X(e[0]) + " " + (k === 0 ? y : (e[1] ? 90 : 30)) + " L" + X(e[0]) + " " + y + " ";
      });
      d += "L" + X(c.samples - 1) + " " + (c.edges[c.edges.length - 1][1] ? 30 : 90);
      svg.appendChild(sv("path", { d: d, class: "ink", "stroke-width": 1.5 }));
      cursor = sv("line", { x1: X(0), x2: X(0), y1: 10, y2: 108, class: "warn", "stroke-width": 1.5 });
      svg.appendChild(cursor);
      svg.appendChild(sv("text", { x: L, y: H - 2 }, "sample 0"));
      svg.appendChild(sv("text", { x: W - 10, y: H - 2, "text-anchor": "end" }, "sample " + (c.samples - 1)));
      holder.appendChild(svg);
    }
    draw();
    var marks = 64;
    function onFrame(k) {
      var c = B.captures[cur]; var idx = Math.round(k * (c.samples - 1) / 63);
      cursor.setAttribute("x1", X(idx)); cursor.setAttribute("x2", X(idx));
      var on = 0, v = 0; c.edges.forEach(function (e) { if (e[0] <= idx) { v = e[1]; } });
      for (var q = 0; q < c.edges.length; q++) { var e = c.edges[q], nx = q + 1 < c.edges.length ? c.edges[q + 1][0] : c.samples; if (e[1]) on += Math.max(0, Math.min(nx, idx + 1) - e[0]); }
      return "Sample " + idx + ": LED 0 is " + (v ? "on" : "off") + ". On for " + on + " of the " + (idx + 1) + " samples so far. The whole capture: " + c.on + " of " + c.samples + " samples on, the model says " + c.model_on + ".";
    }
    var player = Player(root, marks, onFrame, { interval: 220 });
  }


  /* ---------- golden-model trace viewer (problem pages): waveform + values at the cursor + bespoke hero ---------- */
  function fmtv(sg, v) {
    if (sg.kind === "bus") {
      if (sg.radix === "hex") { var hd = sg.width ? Math.ceil(sg.width / 4) : 1; var hs = (v >>> 0).toString(16); if (v < 0) hs = "-" + (-v).toString(16); while (hs.length < hd) hs = "0" + hs; return "0x" + hs; }
      if (sg.radix === "bin") { var bs = (v >>> 0).toString(2); while (sg.width && bs.length < sg.width) bs = "0" + bs; return bs; }
      return String(v);
    }
    return String(v);
  }
  function mountWave(holder, T) {
    var n = T.x.length, LW = 132, CW = Math.max(12, Math.min(28, Math.floor(620 / n))), W = LW + n * CW + 6, RH = 34;
    var H = 22 + T.signals.length * RH;
    var s = sv("svg", { viewBox: "0 0 " + W + " " + H, width: "100%", role: "img", class: "wavesvg",
      "aria-label": "Waveform of " + T.signals.map(function (g) { return g.name; }).join(", ") + " over " + n + " " + T.unit + "s" });
    function X(i) { return LW + i * CW; }
    for (var i = 0; i < n; i += Math.max(1, Math.ceil(n / 12))) s.appendChild(sv("text", { x: X(i) + 2, y: 12 }, T.x[i]));
    T.signals.forEach(function (g, r) {
      var y0 = 22 + r * RH, top = y0 + 5, bot = y0 + RH - 7, mid = (top + bot) / 2;
      s.appendChild(sv("text", { x: 0, y: mid + 4 }, g.name.length > 17 ? g.name.slice(0, 16) + "." : g.name));
      s.appendChild(sv("line", { x1: LW, x2: X(n), y1: y0 + RH - 1, y2: y0 + RH - 1, class: "rule" }));
      var d = "";
      if (g.kind === "bit") {
        g.v.forEach(function (v, k) { var y = v ? top : bot; d += (k ? "L" : "M") + X(k) + " " + y + " L" + X(k + 1) + " " + y + " "; });
        s.appendChild(sv("path", { d: d, class: "ink", "stroke-width": 1.5 }));
      } else if (g.kind === "wave") {
        var lo = g.lo != null ? g.lo : Math.min.apply(null, g.v), hi = g.hi != null ? g.hi : Math.max.apply(null, g.v); if (hi === lo) hi = lo + 1;
        g.v.forEach(function (v, k) { var y = bot - (bot - top) * (v - lo) / (hi - lo); d += (k ? "L" : "M") + (X(k) + CW / 2) + " " + y.toFixed(1) + " "; });
        s.appendChild(sv("path", { d: d, class: "ink", "stroke-width": 1.5 }));
        g.v.forEach(function (v, k) { var y = bot - (bot - top) * (v - lo) / (hi - lo); s.appendChild(sv("circle", { cx: X(k) + CW / 2, cy: y.toFixed(1), r: 1.8, class: "fillink" })); });
      } else {
        var a = 0;
        for (var k = 1; k <= n; k++) {
          if (k === n || g.v[k] !== g.v[a]) {
            var x1 = X(a), x2 = X(k), val = g.v[a], txt = fmtv(g, val), empty = g.kind === "text" ? val === "" : false;
            if (empty) s.appendChild(sv("line", { x1: x1, x2: x2, y1: mid, y2: mid, class: "ink", "stroke-width": 1 }));
            else {
              s.appendChild(sv("path", { d: "M" + x1 + " " + mid + " L" + (x1 + 3) + " " + top + " L" + (x2 - 3) + " " + top + " L" + x2 + " " + mid + " L" + (x2 - 3) + " " + bot + " L" + (x1 + 3) + " " + bot + " Z", class: "ink", "stroke-width": 1.2 }));
              var room = Math.floor((x2 - x1 - 8) / 6.7);
              if (room >= 1) s.appendChild(sv("text", { x: x1 + 5, y: mid + 4 }, txt.length > room ? (room > 2 ? txt.slice(0, room - 1) + "." : "") : txt));
            }
            a = k;
          }
        }
      }
    });
    var shade = sv("rect", { x: X(1), y: 16, width: W, height: H, class: "future" });
    var cur = sv("rect", { x: X(0), y: 16, width: CW, height: H - 16, class: "cursor" });
    s.appendChild(shade); s.appendChild(cur);
    var wrap = el("div", { class: "wavewrap", tabindex: "0" }); wrap.appendChild(s); holder.appendChild(wrap);
    var vals = el("dl", { class: "vals" }); holder.appendChild(vals);
    return function (i) {
      shade.setAttribute("x", X(i + 1)); cur.setAttribute("x", X(i));
      vals.innerHTML = "";
      vals.appendChild(el("div", {}, [el("dt", { text: T.unit }), el("dd", { class: "mono", text: String(T.x[i]) })]));
      T.signals.forEach(function (g) { vals.appendChild(el("div", {}, [el("dt", { text: g.name }), el("dd", { class: "mono", text: g.kind === "text" && g.v[i] === "" ? "none" : fmtv(g, g.v[i]) })])); });
    };
  }
  function sig(T, name) { for (var k = 0; k < T.signals.length; k++) if (T.signals[k].name === name) return T.signals[k].v; return null; }
  function hx(b) { return (b < 16 ? "0" : "") + b.toString(16); }
  var HEROES = {
    t1_elevator_fsm: function (box, T) {
      var F = T.hero.floors, W = 360, FH = 52, H = F * FH + 20, s = sv("svg", { viewBox: "0 0 " + W + " " + H, width: "100%", role: "img", "aria-label": "Lift shaft: car position, door and calls from the model" });
      box.appendChild(s);
      var fl = sig(T, "FLOOR"), st = sig(T, "STATE"), pe = sig(T, "PENDING"), dr = sig(T, "DIR (1 = down)");
      var lamps = [], labels = [];
      for (var f = 0; f < F; f++) {
        var y = 10 + (F - 1 - f) * FH;
        s.appendChild(sv("line", { x1: 60, x2: 300, y1: y + FH, y2: y + FH, class: "rule" }));
        s.appendChild(sv("text", { x: 4, y: y + FH / 2 + 4 }, "floor " + f));
        lamps.push(sv("circle", { cx: 290, cy: y + FH / 2, r: 7, class: "ink", "stroke-width": 1.5 }));
        s.appendChild(lamps[f]);
      }
      s.appendChild(sv("rect", { x: 120, y: 10, width: 90, height: F * FH, class: "ink", "stroke-width": 1 }));
      var car = sv("g", {}), body = sv("rect", { x: 128, width: 74, height: FH - 10, class: "ink", "stroke-width": 2 });
      var dl = sv("rect", { width: 0, height: FH - 18, class: "fillink" }), dr2 = sv("rect", { width: 0, height: FH - 18, class: "fillink" });
      var arrow = sv("text", { x: 228, "text-anchor": "middle" }, "");
      car.appendChild(body); car.appendChild(dl); car.appendChild(dr2); s.appendChild(car); s.appendChild(arrow);
      s.appendChild(sv("text", { x: 290, y: H - 2, "text-anchor": "middle" }, "calls"));
      return function (i) {
        var y = 10 + (F - 1 - fl[i]) * FH + 5, open = st[i] === "door open";
        body.setAttribute("y", y);
        var dw = open ? 14 : 36;
        dl.setAttribute("x", 132); dl.setAttribute("y", y + 4); dl.setAttribute("width", dw);
        dr2.setAttribute("x", 198 - dw); dr2.setAttribute("y", y + 4); dr2.setAttribute("width", dw);
        arrow.setAttribute("y", y + FH / 2); arrow.textContent = st[i] === "moving" ? (dr[i] ? "down" : "up") : (open ? "open" : "");
        lamps.forEach(function (c, f) { c.setAttribute("class", (pe[i] >> f) & 1 ? "fillink" : "ink"); });
      };
    },
    c10_dds_sine: function (box, T) {
      var h = T.hero, W = 600, H = 200, s = sv("svg", { viewBox: "0 0 " + W + " " + H, width: "100%", role: "img", "aria-label": "Phase wheel and sine output from the model" });
      box.appendChild(s);
      var cx = 90, cy = 100, R = 70, N = 1 << h.la;
      s.appendChild(sv("circle", { cx: cx, cy: cy, r: R, class: "ink", "stroke-width": 1 }));
      s.appendChild(sv("text", { x: cx, y: 192, "text-anchor": "middle" }, "phase (" + h.aw + " bits)"));
      var hand = sv("line", { x1: cx, y1: cy, class: "ink", "stroke-width": 2 }); s.appendChild(hand);
      var dot = sv("circle", { r: 5, class: "fillink" }); s.appendChild(dot);
      var X0 = 200, PW = 390, ph = sig(T, "phase"), out = sig(T, "out"), ad = sig(T, "table address");
      s.appendChild(sv("line", { x1: X0, x2: X0 + PW, y1: cy, y2: cy, class: "rule" }));
      s.appendChild(sv("text", { x: X0 + PW, y: 192, "text-anchor": "end" }, "output samples"));
      var stems = [];
      for (var k = 0; k < out.length; k++) {
        var x = X0 + PW * (k + .5) / out.length, y = cy - (R) * out[k] / h.amp;
        var g = sv("g", {}); g.appendChild(sv("line", { x1: x, x2: x, y1: cy, y2: y, class: "ink", "stroke-width": 1 })); g.appendChild(sv("circle", { cx: x, cy: y, r: 2.5, class: "fillink" }));
        stems.push(g); s.appendChild(g);
      }
      var lab = sv("text", { x: cx, y: 18, "text-anchor": "middle" }, ""); s.appendChild(lab);
      return function (i) {
        var a = 2 * Math.PI * ad[i] / N, x = cx + R * Math.cos(a), y = cy - R * Math.sin(a);
        hand.setAttribute("x2", x); hand.setAttribute("y2", y); dot.setAttribute("cx", x); dot.setAttribute("cy", y);
        lab.textContent = "entry " + ad[i] + " of " + N;
        stems.forEach(function (g, k) { g.style.opacity = k <= i ? 1 : .15; });
      };
    },
    c16_nexys_aes_uart: function (box, T) {
      var h = T.hero, W = 420, C = 56, s = sv("svg", { viewBox: "0 0 " + W + " 250", width: "100%", role: "img", "aria-label": "AES state, 4 by 4 bytes, from the model's round functions" });
      box.appendChild(s);
      var cells = [], texts = [];
      for (var c = 0; c < 4; c++) for (var r = 0; r < 4; r++) {
        var x = 10 + c * C, y = 26 + r * C;
        var rc = sv("rect", { x: x, y: y, width: C - 6, height: C - 6, class: "ink", "stroke-width": 1 }), t = sv("text", { x: x + (C - 6) / 2, y: y + C / 2, "text-anchor": "middle", class: "big" }, "");
        s.appendChild(rc); s.appendChild(t); cells[4 * c + r] = rc; texts[4 * c + r] = t;
      }
      var op = sv("text", { x: 250, y: 60, class: "big" }, ""), rd = sv("text", { x: 250, y: 90 }, ""), ch = sv("text", { x: 250, y: 120 }, "");
      s.appendChild(op); s.appendChild(rd); s.appendChild(ch);
      s.appendChild(sv("text", { x: 10, y: 16 }, "state: bytes go down the columns"));
      var rounds = sig(T, "round");
      return function (i) {
        var st = h.states[i], pr = i ? h.states[i - 1] : st, nch = 0;
        for (var k = 0; k < 16; k++) {
          var diff = st[k] !== pr[k]; if (diff) nch++;
          cells[k].setAttribute("class", diff ? "fillink" : "ink"); texts[k].setAttribute("class", diff ? "big inv" : "big"); texts[k].textContent = hx(st[k]);
        }
        op.textContent = h.ops[i]; rd.textContent = "round " + rounds[i]; ch.textContent = i ? nch + " of 16 bytes changed" : "";
      };
    },
    c9_median3x3: function (box, T) {
      var h = T.hero, W = 600, s = sv("svg", { viewBox: "0 0 " + W + " 200", width: "100%", role: "img", "aria-label": "Window presented and median result, from the model" });
      box.appendChild(s);
      s.appendChild(sv("text", { x: 10, y: 16 }, "window presented this clock"));
      s.appendChild(sv("text", { x: 230, y: 16 }, "window from " + h.lat + " clock earlier, sorted"));
      s.appendChild(sv("text", { x: 230 + 4 * 40 + 18, y: 50, "text-anchor": "middle" }, "fifth"));
      var g = [], gt = [];
      for (var k = 0; k < 9; k++) {
        var x = 10 + (k % 3) * 50, y = 26 + Math.floor(k / 3) * 50;
        var r = sv("rect", { x: x, y: y, width: 46, height: 46, class: "pix" }), t = sv("text", { x: x + 23, y: y + 28, "text-anchor": "middle" }, "");
        s.appendChild(r); s.appendChild(t); g.push(r); gt.push(t);
      }
      var srt = [], st2 = [];
      for (var q = 0; q < 9; q++) {
        var x2 = 230 + q * 40, r2 = sv("rect", { x: x2, y: 60, width: 36, height: 36, class: "pix" }), t2 = sv("text", { x: x2 + 18, y: 83, "text-anchor": "middle" }, "");
        s.appendChild(r2); s.appendChild(t2); srt.push(r2); st2.push(t2);
      }
      var box5 = sv("rect", { x: 230 + 4 * 40 - 4, y: 56, width: 44, height: 44, class: "ink", "stroke-width": 2.5 }); s.appendChild(box5);
      var res = sv("text", { x: 230, y: 130, class: "big" }, ""); s.appendChild(res);
      return function (i) {
        var w = h.in[i], so = h.sorted[i];
        for (var k = 0; k < 9; k++) {
          if (w) { g[k].style.fill = "rgb(" + w[k] + "," + w[k] + "," + w[k] + ")"; gt[k].textContent = w[k]; gt[k].setAttribute("class", w[k] > 127 ? "dark" : "light"); }
          else { g[k].style.fill = "none"; gt[k].textContent = ""; }
          if (so) { srt[k].style.fill = "rgb(" + so[k] + "," + so[k] + "," + so[k] + ")"; st2[k].textContent = so[k]; st2[k].setAttribute("class", so[k] > 127 ? "dark" : "light"); }
          else { srt[k].style.fill = "none"; st2[k].textContent = ""; }
        }
        box5.style.opacity = so ? 1 : .2; res.textContent = so ? "median " + so[4] : "no result this clock";
      };
    },
    c14_systolic_matmul: function (box, T) {
      var h = T.hero, W = 600, n = h.rows.length, L = h.lat, s = sv("svg", { viewBox: "0 0 " + W + " 190", width: "100%", role: "img", "aria-label": "Rows entering, in flight for the latency, and results leaving, from the model" });
      box.appendChild(s);
      s.appendChild(sv("text", { x: 10, y: 16 }, "rows waiting"));
      s.appendChild(sv("text", { x: 170, y: 16 }, "in flight for " + L + " clocks"));
      s.appendChild(sv("text", { x: 170, y: 34 }, "(each row times the 4 x 4 weights)"));
      s.appendChild(sv("text", { x: 480, y: 16 }, "results out"));
      var slots = [];
      for (var k = 0; k < L; k++) { var r = sv("rect", { x: 170 + k * 38, y: 70, width: 34, height: 34, class: "ink", "stroke-width": 1 }); s.appendChild(r); slots.push([r, sv("text", { x: 170 + k * 38 + 17, y: 92, "text-anchor": "middle" }, "")]); s.appendChild(slots[k][1]); }
      var waiting = sv("text", { x: 10, y: 92 }, ""), done = sv("text", { x: 480, y: 92 }, ""), last = sv("text", { x: 170, y: 150 }, "");
      s.appendChild(waiting); s.appendChild(done); s.appendChild(last);
      return function (i) {
        var nextIn = 0; for (var t = 0; t <= i; t++) if (h.in[t] != null) nextIn = h.in[t] + 1;
        var outN = 0; for (var t2 = 0; t2 <= i; t2++) if (h.out[t2] != null) outN = h.out[t2] + 1;
        waiting.textContent = nextIn < n ? (n - nextIn) + " rows" : "none";
        done.textContent = outN + " of " + n + " rows";
        slots.forEach(function (sl, k) {
          var row = i - k >= 0 && h.in[i - k] != null ? h.in[i - k] : null;
          sl[0].setAttribute("class", row != null ? "fillink" : "ink"); sl[1].textContent = row != null ? "r" + row : ""; sl[1].setAttribute("class", row != null ? "inv" : "");
        });
        var o = h.out[i]; last.textContent = o != null ? "row " + o + " x W = " + h.C[o].join("  ") : "";
      };
    }
  };
  function mountTrace(root) {
    var T = D.trace; if (!T) return;
    var heroFn = null, art = root.querySelector(".hero-art"), id = root.getAttribute("data-hero");
    if (art && HEROES[id]) { heroFn = HEROES[id](art, T); var hs = art.querySelector("svg"); if (hs) hs.style.maxWidth = id === "t1_elevator_fsm" ? "400px" : "680px"; }
    var wv = mountWave(root.querySelector(".wave"), T);
    Player(root, T.x.length, function (i) { if (heroFn) heroFn(i); wv(i); return T.captions[i]; }, { autoplay: !!heroFn, interval: 900 });
  }
  var tr = document.getElementById("trace"); if (tr) mountTrace(tr);

  /* ---------- problems index: filter by domain, tier, board (the list is complete without script) ---------- */
  (function () {
    var sels = document.querySelectorAll(".filters select"); if (!sels.length) return;
    var cards = document.querySelectorAll(".pcard"), secs = document.querySelectorAll("section.dom"), cnt = document.getElementById("f-count");
    function apply() {
      var f = {}; sels.forEach(function (s) { f[s.dataset.f] = s.value; });
      var shown = 0;
      cards.forEach(function (c) { var ok = (!f.domain || c.dataset.domain === f.domain) && (!f.tier || c.dataset.tier === f.tier) && (!f.board || c.dataset.board === f.board); c.hidden = !ok; if (ok) shown++; });
      secs.forEach(function (s) { s.hidden = !s.querySelector(".pcard:not([hidden])"); });
      if (cnt) cnt.textContent = shown + " of " + cards.length + " shown";
    }
    sels.forEach(function (s) { s.addEventListener("change", apply); });
    document.querySelectorAll(".dombars a.dl").forEach(function (a) {
      a.addEventListener("click", function (e) { var d = document.getElementById("f-domain"); if (!d || !d.querySelector('option[value="' + a.dataset.dom + '"]')) return; e.preventDefault(); d.value = a.dataset.dom; apply(); document.querySelector(".filters").scrollIntoView(); });
    });
    apply();
  })();
  var h = document.getElementById("hero-player"); if (h) mountReplay(h, "hero");
  var r = document.getElementById("replay"); if (r) mountReplay(r, "full");
  var ila = document.getElementById("ila"); if (ila) mountILA(ila);

  /* ---------- flow notes: a bus crossing a two-flop synchroniser (frames from site/flow_model.py) ---------- */
  function mountTear(root) {
    var T = D.flow_notes && D.flow_notes.tear; if (!T) return;
    var bus = "binary", extra = true, Fr = T.configs.binary_extra, p;
    var tog = el("div", { class: "tog" });
    function group(label, opts, cur, set) {
      var g = el("div", { class: "grp", role: "group", "aria-label": label }, [el("span", { text: label })]), bs = [];
      opts.forEach(function (o) {
        var b = el("button", { type: "button", text: o[1], "aria-pressed": String(o[0] === cur) });
        b.onclick = function () { set(o[0]); bs.forEach(function (x, k) { x.setAttribute("aria-pressed", String(opts[k][0] === o[0])); }); };
        bs.push(b); g.appendChild(b);
      });
      tog.appendChild(g);
    }
    group("Bus", [["binary", "Binary counter"], ["gray", "Gray counter"]], bus, function (v) { bus = v; reload(); });
    group("Extra cycle", [[false, "Off"], [true, "On"]], extra, function (v) { extra = v; reload(); });
    root.appendChild(tog);
    var W = 400, svg = sv("svg", { viewBox: "0 0 400 190", role: "img", "aria-label": "Source bus, first flop and second flop of the synchroniser" });
    var defs = sv("defs"); var pat = sv("pattern", { id: "hatchhold", width: 5, height: 5, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" });
    pat.appendChild(sv("rect", { width: 5, height: 5, fill: "var(--bg)" })); pat.appendChild(sv("line", { x1: 0, y1: 0, x2: 0, y2: 5, stroke: "var(--ink)", "stroke-width": 2 }));
    defs.appendChild(pat); svg.appendChild(defs);
    var rowY = [14, 74, 134], names = ["source bus", "flop 1", "flop 2"], cells = [];
    names.forEach(function (n, r) {
      svg.appendChild(sv("text", { x: 6, y: rowY[r] + 23 }, n));
      var row = [];
      for (var j = 0; j < 4; j++) {
        var g = sv("g"), x = 150 + j * 60;
        var rc = sv("rect", { x: x, y: rowY[r], width: 40, height: 36, class: "bit0" });
        var tx = sv("text", { x: x + 16, y: rowY[r] + 23, class: "big" }, "0");
        g.appendChild(rc); g.appendChild(tx); svg.appendChild(g); row.push([rc, tx]);
      }
      cells.push(row);
    });
    [0, 1].forEach(function (r) { for (var j = 0; j < 4; j++) { var x = 170 + j * 60; svg.appendChild(sv("path", { class: "ink", d: "M" + x + " " + (rowY[r] + 36) + " L" + x + " " + (rowY[r + 1]) })); } });
    root.appendChild(svg);
    var cap = el("p", { class: "cap", "aria-live": "polite" }); root.appendChild(cap);
    var ch = sv("svg", { viewBox: "0 0 400 132", role: "img", "aria-label": "Source value and sampled value over the cycles" });
    var X0 = 34, DX = 360 / T.frames, Y = function (v) { return 108 - v * 6; };
    ch.appendChild(sv("text", { x: 6, y: 10 }, "value, 0 to 15"));
    var cursor = sv("rect", { class: "cursor", x: X0, y: 14, width: DX, height: 96 }); ch.appendChild(cursor);
    ch.appendChild(sv("line", { class: "rule", x1: X0, y1: 108, x2: 394, y2: 108 }));
    ch.appendChild(sv("text", { x: 290, y: 126 }, "destination cycle"));
    var lSrc = sv("path", { class: "line-ink" }), lSeen = sv("path", { class: "line-seen" }); ch.appendChild(lSrc); ch.appendChild(lSeen);
    var marks = sv("g"); ch.appendChild(marks);
    ch.appendChild(sv("text", { x: 6, y: 126 }, "cycle 0 at left"));
    root.appendChild(ch);
    var leg = el("p", { class: "small muted", text: "Chart: solid line is the source value, dashed line is the value the destination sees, a ringed point is a torn value." });
    root.appendChild(leg);
    function path(vals) {
      var d = ""; vals.forEach(function (v, t) { var x = X0 + t * DX; d += (t ? "L" : "M") + x.toFixed(1) + " " + Y(v) + " L" + (x + DX).toFixed(1) + " " + Y(v) + " "; });
      return d;
    }
    function reload() {
      Fr = T.configs[bus + "_" + (extra ? "extra" : "plain")];
      lSrc.setAttribute("d", path(Fr.map(function (f) { return f.cur; })));
      lSeen.setAttribute("d", path(Fr.map(function (f) { return f.seen; })));
      while (marks.firstChild) marks.removeChild(marks.firstChild);
      Fr.forEach(function (f, t) { if (f.torn) marks.appendChild(sv("circle", { class: "torn", cx: (X0 + t * DX + DX / 2).toFixed(1), cy: Y(f.seen), r: 5 })); });
      if (p) p.goto(0);
    }
    function draw(rowI, bits, held) {
      for (var j = 0; j < 4; j++) {
        var c = cells[rowI][j], b = bits[j];
        var isHeld = held && held[j];
        c[0].setAttribute("class", isHeld ? "held" : (b ? "bit1" : "bit0"));
        c[1].textContent = b; c[1].setAttribute("class", "big" + (b && !isHeld ? " b1" : ""));
      }
    }
    function frame(i) {
      var f = Fr[i];
      draw(0, f.src); draw(1, f.f1, f.held); draw(2, f.f2);
      cursor.setAttribute("x", (X0 + i * DX).toFixed(1));
      var h = []; f.held.forEach(function (x, k) { if (x) h.push(k + 1); });
      var code = bus === "gray" ? "Gray code" : "binary";
      var c = "Cycle " + i + ": the source value is " + f.cur + " (" + code + " bits " + f.src.join("") + ")" +
        (i % T.hold === 0 && i ? ", just changed from " + f.prev : "") + ". ";
      c += h.length ? "Flop 1 keeps its old value for bit" + (h.length > 1 ? "s " : " ") + h.join(" and ") + " (counting from the left). " : "";
      c += "The destination sees " + f.seen + (f.torn ? ", which is neither " + f.cur + " nor " + f.prev + ": a torn value." : (f.seen === f.cur ? "." : ", the previous value."));
      return c;
    }
    p = Player(root, T.frames, frame, { interval: 700 });
    reload();
  }
  var tr = document.getElementById("tear"); if (tr) mountTear(tr);
  mountDev(); mountEval1();
})();

/* FPGA fabric backdrop on the home hero: columns of logic tiles (CLB), block RAM and DSP columns, I/O at the edges,
   a clock row, and nets routed tile to tile along the channels. Monochrome; static under reduced motion. */
(function () {
  var cv = document.getElementById("fabric");
  if (!cv || !cv.getContext) return;
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var ctx = cv.getContext("2d"), T = 26, cols, rows, kind, nets = [], ink = "#000", W, H, run = true, last = 0, seed = 7;
  function rnd() { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; }
  function colour() { ink = getComputedStyle(document.documentElement).getPropertyValue("--ink").trim() || "#888"; }
  function layout() {
    var r = cv.getBoundingClientRect(), d = Math.min(window.devicePixelRatio || 1, 2);
    W = r.width; H = r.height; cv.width = Math.round(W * d); cv.height = Math.round(H * d); ctx.setTransform(d, 0, 0, d, 0, 0);
    cols = Math.ceil(W / T) + 1; rows = Math.ceil(H / T) + 1; kind = [];
    for (var c = 0; c < cols; c++) kind.push(c === 0 || c === cols - 1 ? "io" : c % 11 === 5 ? "bram" : c % 11 === 9 ? "dsp" : "clb");
  }
  function base() {
    ctx.clearRect(0, 0, W, H); ctx.strokeStyle = ink; ctx.fillStyle = ink; ctx.lineWidth = 1;
    var hrow = Math.floor(rows / 2);
    for (var c = 0; c < cols; c++) {
      var x = c * T, k = kind[c];
      for (var r = 0; r < rows; r++) {
        var y = r * T;
        if (r === hrow) { ctx.globalAlpha = .10; ctx.fillRect(x, y + T / 2 - 1, T, 2); continue; }
        if (k === "clb") { ctx.globalAlpha = .13; ctx.strokeRect(x + 3.5, y + 3.5, T - 12, T - 12); ctx.globalAlpha = .18; ctx.fillRect(x + T - 7, y + T - 7, 3, 3); }
        else if (k === "io") { ctx.globalAlpha = .16; ctx.strokeRect(x + 6.5, y + 6.5, T - 13, T - 13); }
        else if (r % 5 === 0 && r + 5 <= rows) { ctx.globalAlpha = .15; ctx.strokeRect(x + 2.5, y + 2.5, T - 5, 5 * T - 5);
          if (k === "dsp") ctx.strokeRect(x + 2.5, y + 2.5 + 2.5 * T, T - 5, 0.01); }
      }
    }
    ctx.globalAlpha = 1;
  }
  function tile(k) { for (var i = 0; i < 50; i++) { var c = 1 + Math.floor(rnd() * (cols - 2)); if (kind[c] === k || (!k && kind[c] === "clb")) return [c, Math.floor(rnd() * rows)]; } return [1, 1]; }
  function net() {
    var a = tile(rnd() < .15 ? "dsp" : rnd() < .2 ? "bram" : null), b = [Math.max(1, Math.min(cols - 2, a[0] + Math.round((rnd() - .5) * 14))), Math.max(0, Math.min(rows - 1, a[1] + Math.round((rnd() - .5) * 8)))];
    var mid = a[0] + Math.round((b[0] - a[0]) * rnd()), pts = [], ch = function (c, r) { return [c * T + T - 5.5, r * T + T - 5.5]; };
    pts.push(ch(a[0], a[1]), ch(mid, a[1]), ch(mid, b[1]), ch(b[0], b[1]));
    var len = 0; for (var i = 1; i < pts.length; i++) len += Math.abs(pts[i][0] - pts[i - 1][0]) + Math.abs(pts[i][1] - pts[i - 1][1]);
    return { p: pts, a: a, b: b, len: Math.max(len, 1), t: 0, hold: 2.5 + rnd() * 3, speed: 90 + rnd() * 80 };
  }
  function drawNet(n, alpha) {
    var left = Math.min(n.t * n.speed, n.len); ctx.globalAlpha = alpha; ctx.strokeStyle = ink; ctx.fillStyle = ink; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(n.p[0][0], n.p[0][1]);
    for (var i = 1; i < n.p.length && left > 0; i++) {
      var dx = n.p[i][0] - n.p[i - 1][0], dy = n.p[i][1] - n.p[i - 1][1], s = Math.abs(dx) + Math.abs(dy), f = s ? Math.min(1, left / s) : 1;
      ctx.lineTo(n.p[i - 1][0] + dx * f, n.p[i - 1][1] + dy * f); left -= s;
    }
    ctx.stroke();
    ctx.fillRect(n.a[0] * T + 3, n.a[1] * T + 3, T - 11, T - 11);
    if (n.t * n.speed >= n.len) ctx.fillRect(n.b[0] * T + 3, n.b[1] * T + 3, T - 11, T - 11);
    ctx.globalAlpha = 1;
  }
  function frame(now) {
    if (!run) return;
    var dt = Math.min(.05, (now - (last || now)) / 1000); last = now; base();
    while (nets.length < Math.max(6, Math.round(cols * rows / 90))) nets.push(net());
    nets = nets.filter(function (n) {
      n.t += dt; var done = n.len / n.speed, a = .42;
      if (n.t > done + n.hold) a = .42 * (1 - (n.t - done - n.hold) / 1.5);
      if (a <= 0) return false; drawNet(n, a); return true;
    });
    requestAnimationFrame(frame);
  }
  function still() { base(); for (var i = 0; i < 14; i++) { var n = net(); n.t = 1e3; drawNet(n, .35); } }
  function start() { colour(); layout(); nets = []; seed = 7; if (reduce) still(); else { run = true; last = 0; requestAnimationFrame(frame); } }
  start();
  var rt; window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(start, 150); });
  new MutationObserver(function () { colour(); if (reduce) still(); }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  if (window.matchMedia) window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () { colour(); if (reduce) still(); });
  document.addEventListener("visibilitychange", function () { if (reduce) return; run = !document.hidden; if (run) { last = 0; requestAnimationFrame(frame); } });
  if ("IntersectionObserver" in window && !reduce) new IntersectionObserver(function (e) { var v = e[0].isIntersecting; if (v && !run) { run = true; last = 0; requestAnimationFrame(frame); } else if (!v) run = false; }).observe(cv);

})();

/* expertise drawers: expand all / collapse all (shown only with script) and a hash link opens its drawer */
(function () {
  var ctl = document.getElementById("areactl");
  if (!ctl) return;
  ctl.hidden = false;
  var all = function () { return document.querySelectorAll("details.area"); };
  document.getElementById("expand-all").addEventListener("click", function () { all().forEach(function (d) { d.open = true; }); });
  document.getElementById("collapse-all").addEventListener("click", function () { all().forEach(function (d) { d.open = false; }); });
  function openHash() {
    var id = decodeURIComponent((location.hash || "").slice(1)), t = id && document.getElementById(id);
    if (t && t.tagName === "DETAILS") { t.open = true; t.scrollIntoView(); }
  }
  openHash();
  window.addEventListener("hashchange", openHash);
})();
