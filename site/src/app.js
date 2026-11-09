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
      tb.textContent = n === "dark" ? "Light" : "Dark";
    });
    tb.textContent = curTheme() === "dark" ? "Light" : "Dark";
  }

  /* generic player: n steps, play/pause, step, scrub, speed, reset; keyboard when focused; pauses off-screen */
  function Player(root, n, onFrame, opts) {
    opts = opts || {};
    var i = 0, playing = false, timer = null, speed = 1, visible = true, base = opts.interval || 1100;
    var live = root.querySelector(".cap");
    var play = el("button", { type: "button", "aria-label": "Play", text: "Play" });
    var back = el("button", { type: "button", "aria-label": "Step back", text: "Back" });
    var fwd = el("button", { type: "button", "aria-label": "Step forward", text: "Next" });
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
        el("span", { class: "tag run", text: "Running" }),
        el("p", { text: "Running: results after all 57 runs. Nothing is shown here until the last run is scored; the order of the runs is fixed in advance and does not depend on results." })]));
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

  var h = document.getElementById("hero-player"); if (h) mountReplay(h, "hero");
  var r = document.getElementById("replay"); if (r) mountReplay(r, "full");
  var ila = document.getElementById("ila"); if (ila) mountILA(ila);
  mountDev(); mountEval1();
})();
