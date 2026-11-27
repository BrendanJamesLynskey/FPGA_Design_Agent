"use strict";
/* The stage map of the Live page (brief 238): where the agent is, drawn from the recorded events of /api/live/map and moved only when the run's files say it moved.
   Nothing here invents a step or a percentage: every frame is a row the server read from the run folder (navigator/stagemap.py), and the page only draws it.
   Inline SVG and CSS only (the page's CSP allows no inline style and no outside host); the token travels along an SVG path with requestAnimationFrame. */
(function () {
  var COLS = 5, NW = 164, NH = 104, GX = 45, ROWY = [18, 236], VW = 1000, VH = 372, TOKEN_MS = 600;

  function reducedMotion() { try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) { return false; } }
  function roleName(r) { return ({ clarify: "Clarifier", model: "Modeller", tests: "Verifier", rtl: "Designer" })[r] || r; }
  function words(name, w) {                                   // "board-and-device-planning" -> ["board and device", "planning"]
    var out = [], cur = "";
    name.replace(/-/g, " ").split(" ").forEach(function (x) { if (cur && (cur + " " + x).length > w) { out.push(cur); cur = x; } else cur = cur ? cur + " " + x : x; });
    if (cur) out.push(cur);
    return out.slice(0, 3);
  }
  function mins(sec) { return sec < 90 ? Math.round(sec) + " s" : sec < 5400 ? Math.round(sec / 60) + " min" : (sec / 3600).toFixed(1) + " h"; }

  function create(env) {
    var h = env.h, s = env.s, api = env.api, runId = env.runId;
    var data = null, shown = -1, replaying = false, paused = false, speed = 1, timer = null, q = [], busy = false, fetchedAt = 0, tokenRaf = null, gen = 0, lastAnnounce = "";
    var nodes = [], geo = [], arcLayer, edgeLayer, tokenLayer, token, svg, listItems = [], routesList, caption, waitLine, liveRegion, stateLine, ctl, btnReplay, btnPause, selSpeed, progress, srcLine;

    var root = h("section", { class: "stagemap panel", "aria-label": "Stage map" });
    liveRegion = h("div", { class: "sr-only", "aria-live": "polite", role: "status" });
    stateLine = h("p", { class: "map-state" });
    caption = h("p", { class: "map-line", "aria-hidden": "true" });
    waitLine = h("p", { class: "map-wait", hidden: true });
    routesList = h("ul", { class: "map-routes" });
    srcLine = h("p", { class: "src" });
    btnReplay = h("button", { type: "button", on: { click: function () { if (replaying) stopReplay(); else startReplay(); } } }, "Replay");
    btnPause = h("button", { type: "button", hidden: true, on: { click: togglePause } }, "Pause");
    selSpeed = h("select", { "aria-label": "Replay speed", hidden: true, on: { change: function () { speed = parseFloat(selSpeed.value) || 1; } } },
      [["0.5", "0.5x"], ["1", "1x"], ["2", "2x"], ["4", "4x"]].map(function (o) { return h("option", { value: o[0], selected: o[0] === "1" ? true : null }, o[1]); }));
    progress = h("span", { class: "mute" });
    ctl = h("div", { class: "toolbar flush", hidden: true }, btnReplay, btnPause, selSpeed, progress);
    root.appendChild(h("h2", { class: "flush" }, "Where the run is"));
    root.appendChild(stateLine);
    root.appendChild(ctl);
    root.appendChild(liveRegion);

    function build() {
      var m = data.machine, n = m.length, rows = Math.ceil(n / COLS);
      geo = m.map(function (st, i) { var r = Math.floor(i / COLS), c = i % COLS; return { x: c * (NW + GX), y: ROWY[Math.min(r, 1)] + (r > 1 ? (r - 1) * 216 : 0), r: r, c: c }; });
      svg = s("svg", { viewBox: "0 0 " + VW + " " + (rows > 2 ? VH + 216 * (rows - 2) : VH), class: "map-wide", role: "img", "aria-label": "Stage map of the run; the list under it says the same in words" });
      svg.appendChild(s("defs", null, s("marker", { id: "ar-" + runId, viewBox: "0 0 10 10", refX: 8, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" }, s("path", { d: "M0 0 L10 5 L0 10 z", class: "arrow" }))));
      edgeLayer = s("g", null); arcLayer = s("g", null); tokenLayer = s("g", null);
      svg.appendChild(edgeLayer); svg.appendChild(arcLayer);
      nodes = m.map(function (st, i) {
        var g = geo[i], lines = words(st.name, 17);
        var rect = s("rect", { x: g.x, y: g.y, width: NW, height: NH, class: "node-rect" });
        var t0 = s("text", { x: g.x + 10, y: g.y + 18, class: "node-title" }, i + "  " + (lines[0] || ""));
        var t1 = s("text", { x: g.x + 10, y: g.y + 34, class: "node-title" }, lines.slice(1).join(" "));
        var tv = s("text", { x: g.x + 10, y: g.y + 54, class: "m" }, "");
        var ts = s("text", { x: g.x + 10, y: g.y + 73, class: "node-status" }, "");
        var tg = s("text", { x: g.x + 10, y: g.y + 91, class: "m" }, "");
        var role = s("text", { x: g.x + NW - 10, y: g.y + 54, "text-anchor": "end", class: "node-role" }, "");
        var spin = s("g", { class: "spin", hidden: true }, s("circle", { cx: g.x + NW - 18, cy: g.y + 85, r: 7, class: "spin-ring" }), s("path", { d: "M" + (g.x + NW - 18) + " " + (g.y + 78) + " a7 7 0 0 1 7 7", class: "spin-arc" }));
        var ttl = s("title", null, "");
        var grp = s("g", { class: "node muted", "data-n": i }, ttl, rect, t0, t1, tv, ts, tg, role, spin);
        svg.appendChild(grp);
        return { g: grp, rect: rect, tv: tv, ts: ts, tg: tg, role: role, spin: spin, ttl: ttl };
      });
      svg.appendChild(tokenLayer);
      token = s("g", { class: "token", hidden: true }, s("circle", { r: 9, class: "token-ring" }), s("circle", { r: 4.5, class: "token-dot" }));
      tokenLayer.appendChild(token);
      var list = h("ol", { class: "map-list", "aria-label": "Stages" });
      listItems = m.map(function (st, i) { var li = h("li", { class: "muted" }); list.appendChild(li); return li; });
      var oldSvg = root.querySelector("svg"); if (oldSvg) { oldSvg.remove(); root.querySelector("ol").remove(); caption.remove(); waitLine.remove(); routesList.remove(); srcLine.remove(); }
      root.appendChild(svg); root.appendChild(list); root.appendChild(caption); root.appendChild(waitLine);
      root.appendChild(h("h3", { class: "mt2" }, "Routes back")); root.appendChild(routesList); root.appendChild(srcLine);
    }

    function edgePath(a, b, back) {
      var A = geo[a], B = geo[b];
      if (!back && b === a + 1) {
        if (A.r === B.r) return "M" + (A.x + NW) + " " + (A.y + NH / 2) + " H" + B.x;
        return "M" + (A.x + NW / 2) + " " + (A.y + NH) + " V" + (A.y + NH + 24) + " H" + (B.x + NW / 2) + " V" + B.y;
      }
      var ax = A.x + NW / 2, bx = B.x + NW / 2;
      if (A.r === B.r) {
        var dip = 26 + 7 * Math.min(4, Math.abs(a - b)), by = A.y + NH;
        return "M" + ax + " " + by + " C" + ax + " " + (by + dip) + " " + bx + " " + (by + dip) + " " + bx + " " + by;
      }
      if (A.r > B.r) return "M" + ax + " " + A.y + " C" + ax + " " + (A.y - 60) + " " + bx + " " + (B.y + NH + 60) + " " + bx + " " + (B.y + NH);
      return "M" + ax + " " + (A.y + NH) + " C" + ax + " " + (A.y + NH + 60) + " " + bx + " " + (B.y - 60) + " " + bx + " " + B.y;
    }
    function arcLabelPos(a, b) {
      var A = geo[a], B = geo[b], ax = A.x + NW / 2, bx = B.x + NW / 2;
      if (A.r === B.r) return { x: (ax + bx) / 2, y: A.y + NH + 26 + 7 * Math.min(4, Math.abs(a - b)) * 0.75 + 14 };
      return { x: (ax + bx) / 2, y: (A.y + B.y + NH) / 2 + 4 };
    }

    function routesUpTo(idx) {
      var map = {};
      data.frames.forEach(function (f) {
        if (f.i > idx || !f.back || f.from_n === null || f.from_n === undefined) return;
        var k = f.from_n + ">" + f.n;
        map[k] = map[k] || { from: f.from_n, to: f.n, count: 0, label: "" };
        map[k].count++; map[k].label = f.route;
      });
      return Object.keys(map).map(function (k) { return map[k]; });
    }

    function frameAt(idx) { for (var i = 0; i < data.frames.length; i++) if (data.frames[i].i === idx) return data.frames[i]; return null; }
    function frozen() { return data.status !== "active" && !replaying; }

    function render(f, flashKind) {
      var m = data.machine, noRun = !f;
      var st = f ? f.st : m.map(function () { return [0, null, 0, 0]; });
      var finished = f && f.kind === "end";
      var moving = !frozen() && f && f.open;
      svg.classList.toggle("frozen", !moving);
      var arcs = f ? routesUpTo(f.i) : [];
      edgeLayer.textContent = "";
      m.forEach(function (stg, i) { if (i === 0) return; edgeLayer.appendChild(s("path", { d: edgePath(i - 1, i, false), class: "edge" + (st[i][0] > 0 ? " used" : ""), "marker-end": "url(#ar-" + runId + ")" })); });
      arcLayer.textContent = "";
      arcs.forEach(function (a) {
        var p = arcLabelPos(a.from, a.to);
        arcLayer.appendChild(s("path", { d: edgePath(a.from, a.to, true), class: "arc", "marker-end": "url(#ar-" + runId + ")" }));
        arcLayer.appendChild(s("text", { x: p.x, y: p.y, "text-anchor": "middle", class: "arc-label" }, "↩ " + a.label + (a.count > 1 ? " (x" + a.count + ")" : "")));
      });
      routesList.textContent = "";
      if (!arcs.length) routesList.appendChild(h("li", { class: "mute" }, "none so far"));
      arcs.forEach(function (a) { routesList.appendChild(h("li", null, "↩ " + a.label + (a.count > 1 ? ", " + a.count + " times" : ""))); });
      m.forEach(function (stg, i) {
        var v = st[i][0], res = st[i][1], gp = st[i][2], gf = st[i][3], N = nodes[i], li = listItems[i];
        var isCur = f && f.cur === i, working = isCur && f.open && !finished, waiting = working && f.wait;
        var cls = "node " + (working ? (waiting ? "waiting" : "working") : res === "pass" ? "pass" : res === "fail" ? "fail" : v ? "visited" : "muted");
        if (isCur && !finished && !working) cls += " here";
        if (flashKind && f && f.n === i) cls += " flash-" + flashKind;
        N.g.setAttribute("class", cls);
        var visitTxt = v ? "visit " + v + " of " + stg.limit : "";
        var statusTxt = working ? (waiting ? "⏸ waiting" : "▶ working") + (res === "fail" ? " (last: ✗)" : res === "pass" ? " (last: ✓)" : "") : res === "pass" ? "✓ pass" : res === "fail" ? "✗ fail" : v ? "visited" : "○ not reached";
        var gateTxt = gp + gf ? "gate checks: " + gp + " ✓  " + gf + " ✗" : "";
        N.tv.textContent = visitTxt; N.ts.textContent = statusTxt; N.tg.textContent = gateTxt;
        N.role.textContent = working && f.role ? roleName(f.role) : "";
        var tool = working && f.step && !frozen();
        N.spin.toggleAttribute("hidden", !tool);
        N.ttl.textContent = stg.name + ": " + (visitTxt ? visitTxt + ", " : "") + statusTxt + (gateTxt ? ", " + gateTxt : "") + (working && f.role ? ", role " + roleName(f.role) : "") + (tool ? ", tool running: " + f.step.what : "");
        li.setAttribute("class", cls.replace("node ", ""));
        li.textContent = "";
        li.appendChild(h("strong", null, i + " " + stg.name.replace(/-/g, " ")));
        li.appendChild(document.createTextNode(" — " + (visitTxt ? visitTxt + ", " : "") + statusTxt + (working && f.role ? ", " + roleName(f.role) : "") + (tool ? ", running " + f.step.what : "") + (gateTxt ? " — " + gateTxt : "")));
      });
      var ageNow = data.age_s === null || data.age_s === undefined ? null : data.age_s + (Date.now() - fetchedAt) / 1000;
      var state;
      if (noRun) state = "No stage recorded yet.";
      else if (finished) state = "Finished. " + f.stop;
      else if (replaying) state = "Replay of the recorded events: " + f.line;
      else if (data.status === "finished") state = f.line;
      else if (data.status === "idle") state = "No activity for " + (ageNow === null ? "an unknown time" : mins(ageNow)) + ". The map is still; the last recorded event was: " + f.line;
      else state = f.line;
      var wait = f && f.wait && !finished ? f.wait.why : "";
      waitLine.toggleAttribute("hidden", !wait); waitLine.textContent = wait ? "⏸ " + wait : "";
      var live = replaying ? "replay" : data.status === "active" ? "live" : data.status === "finished" ? "finished" : "idle";
      stateLine.textContent = ""; stateLine.appendChild(h("span", { class: "st " + (live === "live" ? "ok" : live === "idle" ? "warn" : live === "replay" ? "warn" : "unknown") }, live.toUpperCase())); stateLine.appendChild(document.createTextNode("  " + state));
      caption.textContent = "";
      var say;
      if (noRun) say = "No stage recorded yet";
      else if (finished) say = "Run finished: " + f.stop;
      else { var cs = m[f.cur === null ? 0 : f.cur]; say = "Stage " + f.cur + ", " + (cs ? cs.name.replace(/-/g, " ") : "") + ", visit " + (st[f.cur][0]) + " of " + (cs ? cs.limit : "") + (f.role ? ", role " + roleName(f.role) : "") + (wait ? ", " + wait : "") + (f.back ? ", route back: " + f.route : ""); }
      if (say !== lastAnnounce) { lastAnnounce = say; liveRegion.textContent = say; }
      srcLine.textContent = "from " + data.source.dir + " (" + data.source.files.join(", ") + "). " + data.source.note + (data.dropped_frames ? " The first " + data.dropped_frames + " events are not shown." : "");
      if (replaying) progress.textContent = "event " + (f ? f.i + 1 : 0) + " of " + data.frames.length;
    }

    function tokenTo(f, dur, done) {
      var from = f.from_n, to = f.n;
      if (reducedMotion() || from === null || from === undefined || !geo[from] || !geo[to] || from === to) { done(); return; }
      var d = edgePath(from, to, !!f.back || to < from);
      var path = s("path", { d: d });
      var len = path.getTotalLength ? (svg.appendChild(path), path.getTotalLength()) : 0;
      token.setAttribute("class", "token" + (f.back ? " back" : ""));
      token.removeAttribute("hidden");
      var t0 = null, myGen = gen;
      function step(ts) {
        if (myGen !== gen) { path.remove(); token.setAttribute("hidden", ""); return; }
        if (t0 === null) t0 = ts;
        var k = Math.min(1, (ts - t0) / dur), pt = path.getPointAtLength(len * k);
        token.setAttribute("transform", "translate(" + pt.x + " " + pt.y + ")");
        if (k < 1) tokenRaf = requestAnimationFrame(step); else { path.remove(); token.setAttribute("hidden", ""); done(); }
      }
      tokenRaf = requestAnimationFrame(step);
    }

    /* show one frame; with animation, a stage entry first moves the token from the old stage and then lights the new one */
    function showFrame(idx, animate, gap, done) {
      var f = frameAt(idx);
      if (!f) { done && done(); return; }
      var prev = frameAt(idx - 1);
      var fin = function () { shown = idx; render(f, animate && f.flash ? f.flash : null); if (animate && f.flash && !reducedMotion()) setTimeout(function () { if (shown === idx) render(f, null); }, 750); setTimeout(function () { done && done(); }, Math.max(0, gap)); };
      if (animate && f.kind === "enter" && f.from_n !== null && f.from_n !== undefined) {
        if (prev) render(prev, null);
        tokenTo(f, Math.min(TOKEN_MS, Math.max(150, gap * 0.8)), fin);
      } else fin();
    }

    function pump() {
      if (busy || !q.length || replaying) return;
      var idx = q.shift(); busy = true;
      showFrame(idx, true, 150, function () { busy = false; pump(); });
    }

    function startReplay() {
      if (!data || !data.can_replay) return;
      replaying = true; paused = false; gen++; q = []; busy = false;
      btnReplay.textContent = "Stop replay"; btnPause.hidden = false; selSpeed.hidden = false; btnPause.textContent = "Pause";
      var i = 0;
      function next() {
        if (!replaying) return;
        if (paused) { timer = setTimeout(next, 150); return; }
        if (i >= data.frames.length) { stopReplay(); return; }
        var f = data.frames[i++], base = f.kind === "enter" ? 1000 : f.kind === "role" ? 650 : 750, gap = base / speed;
        showFrame(f.i, true, gap, function () { next(); });
      }
      render(null, null);
      next();
    }
    function stopReplay() {
      replaying = false; paused = false; gen++; clearTimeout(timer); token && token.setAttribute("hidden", "");
      btnReplay.textContent = "Replay"; btnPause.hidden = true; selSpeed.hidden = true; progress.textContent = "";
      if (data) { var last = data.frames[data.frames.length - 1]; shown = last ? last.i : -1; render(last || null, null); }
    }
    function togglePause() { paused = !paused; btnPause.textContent = paused ? "Resume" : "Pause"; }

    function apply(d) {
      var first = !data;
      data = d; fetchedAt = Date.now();
      if (first || !nodes.length || nodes.length !== d.machine.length) { build(); }
      ctl.toggleAttribute("hidden", !d.can_replay);
      if (replaying) return;
      var last = d.frames[d.frames.length - 1];
      if (!last) { render(null, null); return; }
      if (first || shown < 0) { shown = last.i; render(last, null); return; }
      var fresh = d.frames.filter(function (f) { return f.i > shown && q.indexOf(f.i) < 0; }).map(function (f) { return f.i; });
      if (fresh.length > 12) { q = []; gen++; shown = last.i; render(last, null); return; }
      if (fresh.length) { q = q.concat(fresh); pump(); } else if (!busy && !q.length) render(frameAt(shown) || last, null);
    }
    function refresh() {
      return api("/api/live/map?id=" + encodeURIComponent(runId)).then(apply, function (e) { stateLine.textContent = "Could not load the stage map: " + (e.message || e); });
    }
    refresh();
    return { el: root, refresh: refresh, destroy: function () { gen++; replaying = false; clearTimeout(timer); if (tokenRaf) cancelAnimationFrame(tokenRaf); } };
  }
  window.FdaStageMap = { create: create, _words: words };
})();
