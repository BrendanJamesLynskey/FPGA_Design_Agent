"use strict";
(function () {
  var PAGES = [["project", "Project"], ["timing", "Timing"], ["runs", "Runs"], ["live", "Live"], ["start", "Start"], ["board", "Board"], ["measure", "Measurements"], ["trace", "Traceability"], ["health", "Health"], ["models", "Models"]];
  var main = document.getElementById("main");
  var state = { theme: "dark", scope: {}, request: "", project: null, measureTab: "eye", capA: null, capB: null, session: 0, lastFocus: null };

  /* ---------- helpers ---------- */
  function h(tag, attrs) {
    var el = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === "class") el.className = v;
      else if (k === "on") Object.keys(v).forEach(function (e) { el.addEventListener(e, v[e]); });
      else if (k === "text") el.textContent = v;
      else el.setAttribute(k, v === true ? "" : v);
    });
    for (var i = 2; i < arguments.length; i++) add(el, arguments[i]);
    return el;
  }
  function add(el, c) {
    if (c === null || c === undefined || c === false) return;
    if (Array.isArray(c)) c.forEach(function (x) { add(el, x); });
    else el.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
  }
  var NS = "http://www.w3.org/2000/svg";
  function s(tag, attrs) {
    var el = document.createElementNS(NS, tag);
    if (attrs) Object.keys(attrs).forEach(function (k) { if (attrs[k] !== null && attrs[k] !== undefined) el.setAttribute(k, attrs[k]); });
    for (var i = 2; i < arguments.length; i++) { var c = arguments[i]; if (c !== null && c !== undefined && c !== false) el.appendChild(typeof c === "object" ? c : document.createTextNode(String(c))); }
    return el;
  }
  function api(path) {
    return fetch(path, { credentials: "same-origin" }).then(function (r) {
      return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || r.statusText); return j; }, function () { throw new Error(r.status + " " + r.statusText); });
    });
  }
  var navValue = null;
  function post(path, body) {
    var tok = navValue ? Promise.resolve(navValue) : api("/api/session").then(function (j) { navValue = j.nav_value; return navValue; });
    return tok.then(function (t) {
      return fetch(path, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-Navigator-Token": t }, body: JSON.stringify(body || {}) }).then(function (r) { return r.json(); });
    });
  }
  var timers = [];
  function every(ms, fn) { var id = setInterval(fn, ms); timers.push(id); }
  function clearTimers() { timers.forEach(clearInterval); timers = []; }
  function num(x, d) { return x === null || x === undefined ? "not recorded" : (typeof x === "number" ? (d === undefined ? String(x) : x.toFixed(d)) : String(x)); }
  function short(x, n) { return x ? String(x).slice(0, n || 12) : ""; }
  function fmtBER(x) { if (x === null || x === undefined) return "-"; var e = Math.floor(Math.log10(x)); return (x / Math.pow(10, e)).toFixed(1) + "e" + e; }
  function srcLine(src, label) {
    if (!src) return h("p", { class: "src" }, (label || "source") + ": not recorded");
    return h("p", { class: "src" }, (label || "source") + ": ",
      h("button", { type: "button", on: { click: function () { openRecord(src.file); } }, "aria-label": "Show record " + src.file }, src.file),
      " ", src.date ? "(" + src.date + (src.date_from === "recorded" ? ", recorded in the file" : ", file date") + ")" : "", src.key ? " key " + src.key : "");
  }
  function loading(msg) { return h("p", { class: "mute" }, msg || "Loading"); }
  function fail(e) { return h("div", { class: "banner" }, h("strong", null, "Could not load. "), e.message || String(e)); }
  function table(head, rows, opts) {
    opts = opts || {};
    var t = h("table", null, h("thead", null, h("tr", null, head.map(function (c, i) { return h("th", { class: (opts.num || []).indexOf(i) >= 0 ? "num" : null }, c); }))),
      h("tbody", null, rows.map(function (r) {
        var cells = r.cells || r;
        var tr = h("tr", { class: r.onclick ? "click" : null, tabindex: r.onclick ? "0" : null, on: r.onclick ? { click: r.onclick, keydown: function (e) { if (e.key === "Enter") r.onclick(); } } : null },
          cells.map(function (c, i) { return h("td", { class: (opts.num || []).indexOf(i) >= 0 ? "num" : null }, c); }));
        return tr;
      })));
    return h("div", { class: "scroll" }, t);
  }
  function stat(status) { return h("span", { class: "st " + status }, status === "not-run" ? "NOT RUN" : status.toUpperCase()); }

  /* ---------- drawer ---------- */
  var drawer = document.getElementById("drawer"), scrim = document.getElementById("scrim");
  function openDrawer(title, body) {
    state.lastFocus = document.activeElement;
    document.getElementById("drawer-title").textContent = title;
    var b = document.getElementById("drawer-body"); b.textContent = ""; add(b, body);
    drawer.hidden = false; scrim.hidden = false;
    document.getElementById("drawer-close").focus();
  }
  function closeDrawer() { drawer.hidden = true; scrim.hidden = true; if (state.lastFocus && state.lastFocus.focus) state.lastFocus.focus(); }
  document.getElementById("drawer-close").addEventListener("click", closeDrawer);
  scrim.addEventListener("click", closeDrawer);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !drawer.hidden) closeDrawer(); });
  function openRecord(file) {
    openDrawer(file, loading());
    api("/api/record?file=" + encodeURIComponent(file)).then(function (r) {
      var b = document.getElementById("drawer-body"); b.textContent = "";
      add(b, [h("p", { class: "src" }, r.date ? "committed or modified " + r.date + ", " + r.bytes + " bytes" : r.bytes + " bytes"),
        h("pre", { class: "cmd" }, r.lines.join("\n")), r.lines.length >= 6000 ? h("p", { class: "mute" }, "Shown up to line 6000.") : null]);
    }, function (e) { var b = document.getElementById("drawer-body"); b.textContent = ""; add(b, fail(e)); });
  }

  /* ---------- project ---------- */
  var TRUST = ["none", "documented", "verified", "built"];
  function meter(t) { var n = TRUST.indexOf(t); return h("span", { class: "meter", title: "trust: " + t }, [1, 2, 3].map(function (k) { return h("i", { class: k <= n ? "on" : null }); })); }
  function pageProject() {
    var root = h("div", null, h("h1", null, "Project"), loading());
    main.textContent = ""; main.appendChild(root);
    api("/api/projects").then(function (pl) {
      var projects = pl.projects;
      if (!projects.length) { root.textContent = ""; add(root, [h("h1", null, "Project"), h("p", null, "No design in this repository has a project.yaml, so there is no managed project to show. A design gets one with `flow`'s converter (agent.core.managed.from_design).")]); return; }
      if (!state.project || !projects.some(function (p) { return p.name === state.project; })) state.project = projects[0].name;
      loadProject(root, projects);
    }, function (e) { root.textContent = ""; add(root, [h("h1", null, "Project"), fail(e)]); });
  }
  function loadProject(root, projects) {
    api("/api/project?name=" + encodeURIComponent(state.project)).then(function (d) {
      var comps = d.components, sel = state.scope[state.project] || (state.scope[state.project] = []);
      var cmdBox = h("pre", { class: "cmd", id: "cmd" }), res = h("div", { class: "panel", "aria-live": "polite" });
      function refreshScope() {
        var q = "/api/scope?project=" + encodeURIComponent(state.project) + "&components=" + encodeURIComponent(sel.join(",")) + "&request=" + encodeURIComponent(state.request);
        api(q).then(function (r) {
          cmdBox.textContent = r.command.map(function (a) { return /[\s<>]/.test(a) ? "\"" + a + "\"" : a; }).join(" ");
          res.textContent = "";
          if (r.ask) add(res, [h("h3", null, "The agent would ask"), h("p", null, r.ask)]);
          else add(res, [h("h3", null, "What this scope allows"),
            h("dl", null, h("dt", null, "may edit"), h("dd", null, (r.will_touch || []).join(", ") || "nothing"),
              h("dt", null, "read only (frozen)"), h("dd", null, (r.read_only || []).join(", ") || "none"),
              h("dt", null, "owned, out of scope"), h("dd", null, (r.not_in_scope_owned || []).join(", ") || "none"),
              h("dt", null, "scope source"), h("dd", null, r.source === "default" ? "default: every owned component (no component picked)" : r.source))]);
          (r.notes || []).forEach(function (n) { add(res, h("p", { class: "mute" }, n)); });
        }, function (e) { res.textContent = ""; add(res, fail(e)); });
      }
      function nodeEl(n) {
        var c = comps[n.name];
        var cb = h("input", { type: "checkbox", disabled: !c.selectable, checked: sel.indexOf(c.name) >= 0, title: c.selectable ? "add to the scope" : c.not_selectable_why, "aria-label": "Include " + c.name + " in the scope",
          on: { change: function () { var i = sel.indexOf(c.name); if (this.checked && i < 0) sel.push(c.name); if (!this.checked && i >= 0) sel.splice(i, 1); li.firstChild.classList.toggle("selected", this.checked); refreshScope(); } } });
        var box = h("div", { class: "node " + c.ownership + (sel.indexOf(c.name) >= 0 ? " selected" : "") }, cb,
          h("button", { type: "button", class: "name", on: { click: function () { openComponent(d, c); } } }, c.name),
          h("span", { class: "tag strong" }, c.ownership), h("span", { class: "tag" }, c.level.replace("_", " ")),
          h("span", { class: "tag" }, meter(c.trust), c.trust),
          h("span", { class: "mute mono" }, (c.module || "") + (c.instance ? "  " + c.instance : "")));
        var li = h("li", null, box);
        if (n.children.length) li.appendChild(h("ul", null, n.children.map(nodeEl)));
        return li;
      }
      root.textContent = "";
      add(root, [
        h("h1", null, d.project.name),
        h("p", { class: "mute" }, "top module ", h("code", null, d.project.top), "; a file in no component is ", h("strong", null, d.project.unclaimed), ". This page only builds the command; the Start page starts a run with the same guards as the command line."),
        projects.length > 1 ? h("div", { class: "toolbar" }, h("label", null, "Project ", h("select", { on: { change: function () { state.project = this.value; loadProject(root, projects); } } },
          projects.map(function (p) { return h("option", { value: p.name, selected: p.name === state.project }, p.name); })))) : null,
        srcLine(d.source, "manifest"),
        h("div", { class: "legend", "aria-label": "Legend" },
          ["owned", "frozen", "excluded"].map(function (k) { return h("span", { title: d.legend.ownership[k] }, h("i", { class: "sw " + k }), k + ": " + d.legend.ownership[k]); })),
        h("p", { class: "mute" }, "Level is the form the component arrives in. Trust is computed from its evidence, never declared: ", meter("none"), "none, ", meter("documented"), "documented, ", meter("verified"), "verified, ", meter("built"), "built."),
        h("div", { class: "cols" },
          h("div", null, h("h2", null, "Hierarchy"), h("ul", { class: "tree" }, d.tree.map(nodeEl)),
            h("p", { class: "mute" }, "Tick the components a request may touch. Frozen and excluded components cannot be ticked. Click a name for its drawer.")),
          h("div", null, h("h2", null, "Scope"),
            h("label", null, "Change request (optional) ", h("input", { type: "text", class: "fullw", placeholder: "e.g. shorten the verdict latency", value: state.request, on: { input: function () { state.request = this.value; clearTimeout(state.t); state.t = setTimeout(refreshScope, 250); } } })),
            h("h3", { class: "mt" }, "The command"), cmdBox,
            h("button", { type: "button", on: { click: function (e) { var b = e.target; navigator.clipboard && navigator.clipboard.writeText(cmdBox.textContent).then(function () { b.textContent = "Copied"; setTimeout(function () { b.textContent = "Copy command"; }, 1500); }, function () { b.textContent = "Copy failed: select it by hand"; }); } } }, "Copy command"),
            h("p", { class: "mute" }, "Run it in a terminal. The agent resolves the scope itself; this page does not start it."), res))]);
      refreshScope();
    }, function (e) { root.textContent = ""; add(root, [h("h1", null, "Project"), fail(e)]); });
  }
  function openComponent(d, c) {
    var ev = c.evidence.map(function (e) { return [h("button", { type: "button", class: "name", disabled: !e.exists, on: { click: function () { openRecord(e.file); } } }, e.file), e.what, e.exists ? (e.date || "") : "missing"]; });
    openDrawer(c.name, [
      h("p", null, h("span", { class: "tag strong" }, c.ownership), " ", h("span", { class: "tag" }, c.level.replace("_", " ")), " ", h("span", { class: "tag" }, meter(c.trust), c.trust)),
      c.description ? h("p", null, c.description) : null,
      h("p", { class: "mute" }, d.legend.ownership[c.ownership] + "."),
      h("h3", null, "Trust: " + c.trust), c.why_not_higher.length ? h("ul", null, c.why_not_higher.map(function (w) { return h("li", null, w); })) : h("p", null, "Every condition for this label is met on the current content."),
      h("h3", { class: "mt2" }, "Interface contract"),
      c.interface.ports.length ? table(["port", "dir", "width"], c.interface.ports.map(function (p) { return [p.name, p.dir, String(p.width === undefined ? 1 : p.width)]; }), { num: [2] }) : h("p", { class: "mute" }, "No contract is declared, so a change to this component's ports is not checked against one."),
      c.interface.clocks.length ? h("p", null, "clocks: ", h("code", null, JSON.stringify(c.interface.clocks))) : null,
      c.interface.resets.length ? h("p", null, "resets: ", h("code", null, JSON.stringify(c.interface.resets))) : null,
      c.interface.timing_budgets.length ? table(["budget", "dir", "max ns"], c.interface.timing_budgets.map(function (b) { return [b.name, b.dir, String(b.max_ns)]; }), { num: [2] }) : null,
      h("h3", { class: "mt2" }, "Provenance"),
      Object.keys(c.provenance).length ? h("dl", null, Object.keys(c.provenance).map(function (k) { return [h("dt", null, k), h("dd", { class: "mono" }, String(c.provenance[k]))]; }))
        : h("p", { class: "mute" }, "None recorded."),
      c.placement ? h("p", null, "placement: ", h("code", null, JSON.stringify(c.placement))) : null,
      h("h3", { class: "mt2" }, "Where it lives"),
      h("dl", null, h("dt", null, "paths"), h("dd", { class: "mono" }, c.paths.join(", ")), h("dt", null, "instance"), h("dd", { class: "mono" }, c.instance || "(top)"), h("dt", null, "build sources"), h("dd", { class: "mono" }, c.build_sources.join(", ") || "none")),
      c.approved_contract_change ? h("p", { class: "banner" }, "The owner has approved a change to this contract.") : null,
      h("h3", { class: "mt2" }, "Evidence files"),
      ev.length ? table(["file", "what", "date"], ev) : h("p", { class: "mute" }, "none")
    ]);
  }

  /* ---------- timing ---------- */
  function chainChart(L) {
    var W = 1100, padL = 20, padR = 20, barY = 52, barH = 38, total = Math.max(L.total_clocks, 1);
    var x = function (c) { return padL + (c / total) * (W - padL - padR); };
    var svg = s("svg", { viewBox: "0 0 " + W + " 150", role: "img", "aria-label": "Latency chain: " + L.total_clocks + " clocks, " + L.total_ns + " ns" },
      s("defs", null,
        s("pattern", { id: "p-rx", width: 6, height: 6, patternUnits: "userSpaceOnUse" }, s("rect", { width: 6, height: 6, fill: "var(--fill3)" }), s("path", { d: "M0 6L6 0", stroke: "var(--rule2)" })),
        s("pattern", { id: "p-cdc", width: 6, height: 6, patternUnits: "userSpaceOnUse" }, s("rect", { width: 6, height: 6, fill: "var(--bg)" }), s("path", { d: "M0 0L6 6M0 6L6 0", stroke: "var(--ink)", "stroke-width": 1 }))));
    var fillFor = function (d) { return d === "rx" ? "url(#p-rx)" : d.indexOf("->") >= 0 ? "url(#p-cdc)" : d === "tx" ? "var(--fill2)" : "var(--bg)"; };
    var tick = Math.max(1, Math.round(total / 13));
    for (var c = 0; c <= total; c += tick) {
      svg.appendChild(s("line", { x1: x(c), x2: x(c), y1: 28, y2: barY, class: "gr" }));
      svg.appendChild(s("text", { x: x(c), y: 16, "text-anchor": "middle" }, c + " clk"));
      svg.appendChild(s("text", { x: x(c), y: 27, "text-anchor": "middle", class: "m" }, (c * L.period_ns).toFixed(0) + " ns"));
    }
    var prev = 0, labels = 0;
    L.stages.forEach(function (st) {
      var c0 = prev, c1 = prev + (st.clocks || 0); prev = c1;
      var g = s("g", null, s("title", null, st.id + ": " + (st.clocks === null ? "?" : st.clocks) + " clocks, " + num(st.ns) + " ns, domain " + st.domain));
      if (st.clocks > 0) g.appendChild(s("rect", { x: x(c0) + 0.5, y: barY, width: Math.max(1, x(c1) - x(c0) - 1), height: barH, fill: fillFor(st.domain), stroke: st.timing_critical ? "var(--ink)" : "var(--rule2)", "stroke-width": st.timing_critical ? 3 : 1 }));
      else g.appendChild(s("line", { x1: x(c0), x2: x(c0), y1: barY - 4, y2: barY + barH + 4, stroke: "var(--ink)", "stroke-width": 2, "stroke-dasharray": "3 2" }));
      var lx = x(c0) + (st.clocks > 0 ? (x(c1) - x(c0)) / 2 : 0), ly = barY + barH + 14 + (labels % 3) * 13; labels++;
      g.appendChild(s("line", { x1: lx, x2: lx, y1: barY + barH, y2: ly - 9, class: "gr" }));
      g.appendChild(s("text", { x: lx, y: ly, "text-anchor": "middle" }, st.id + (st.clocks === null ? "" : " " + st.clocks)));
      svg.appendChild(g);
    });
    return svg;
  }
  function pageTiming() {
    var root = h("div", null, h("h1", null, "Latency and timing"), loading()); main.textContent = ""; main.appendChild(root);
    var design = state.design || "";
    api("/api/latency" + (design ? "?design=" + encodeURIComponent(design) : "")).then(function (d) {
      var L = d.latency; root.textContent = "";
      add(root, h("h1", null, "Latency and timing"));
      if (d.designs.length > 1) add(root, h("div", { class: "toolbar" }, h("label", null, "Design ", h("select", { on: { change: function () { state.design = this.value; pageTiming(); } } }, d.designs.map(function (n) { return h("option", { value: n, selected: n === (L && L.design) }, n); })))));
      if (!L) add(root, h("p", null, "No design in this repository declares a latency chain (latency_stages.yaml)."));
      else if (L.error) add(root, [h("h2", null, L.design), h("div", { class: "banner" }, L.error)]);
      else {
        add(root, [h("h2", null, L.title),
          h("div", { class: "kpi" }, h("div", null, h("b", null, L.total_clocks), h("span", null, "clocks, simulated worst case" + ((L.chains || []).filter(function (c) { return c.is_stage_table; }).length ? " (" + L.chains.filter(function (c) { return c.is_stage_table; })[0].label.split(";")[0].split(" (")[0] + ")" : ""))), h("div", null, h("b", null, L.total_ns), h("span", null, "ns at " + L.period_ns + " ns a clock")),
            h("div", null, h("b", null, L.reconciled ? "yes" : "NO"), h("span", null, "stages add up to the bench"))),
          (L.chains || []).length > 1 ? [h("h3", { class: "mt" }, "Chains recorded for this design"), table(["clocks", "build", "stage table here", "record"], L.chains.map(function (c) { return { cells: [c.clocks === null ? "not recorded" : String(c.clocks), c.label, c.is_stage_table ? "yes" : "no", c.file], onclick: function () { openRecord(c.file); } }; }), { num: [0] }),
            h("p", { class: "mute" }, "The stage table and the chart below describe one chain only: the one marked yes. A build without a stage table has its total from the same bench but no per-stage breakdown.")] : null,
          L.problems.length ? h("div", { class: "banner" }, h("strong", null, "Not reconciled. "), L.problems.join("; ")) : null,
          chainChart(L),
          h("p", { class: "mute" }, "Bar width is the clocks a stage adds (simulation, in-phase clocks, worst case). Hatched: receive clock. Crossed: the clock crossing. Solid grey: transmit clock. A dashed tick is a stage that adds no clock. A heavy outline is timing-critical (worst setup slack below the threshold); the chain is latency-critical and the two are different paths."),
          srcLine(L.sources.stages, "stage file"), srcLine(L.sources.simulation, "simulated clocks"), L.sources.slack ? srcLine(L.sources.slack, "post-route slack") : h("p", { class: "src" }, L.sources.slack_missing_note),
          table(["stage", "domain", "kind", "clocks", "cumulative", "ns", "setup slack ns"], L.stages.map(function (st) {
            return { cells: [st.id, st.domain, st.kind, num(st.clocks), num(st.cumulative_clocks), num(st.ns), st.netlist ? num(st.netlist.setup_slack_ns) + (st.timing_critical ? " (critical)" : "") : "not recorded"], onclick: function () { openStage(L, st); } };
          }), { num: [3, 4, 5, 6] })]);
        if (L.board) add(root, [h("h2", null, "Board measurement"), h("dl", null, h("dt", null, "echo E (clocks)"), h("dd", null, num(L.board.E_clocks)), h("dt", null, "loop L (clocks)"), h("dd", null, num(L.board.L_clocks)), h("dt", null, "fibre one way"), h("dd", null, num(L.board.fibre_ns, 1) + " ns")),
          h("p", { class: "mute" }, L.board_note), h("p", { class: "src" }, "record: ", h("button", { type: "button", on: { click: function () { openRecord("results/" + L.board.file); } } }, "results/" + L.board.file))]);
        else add(root, h("p", { class: "mute" }, L.board_note + ". Board sessions that are recorded are under Measurements."));
      }
      add(root, [h("h2", null, "Builds: timing, resources, power"), h("p", { class: "mute" }, "Post-route digests recorded under results/*/builds/. WNS and WHS are the worst setup and hold slack; a negative one fails timing."),
        table(["build", "WNS ns", "WHS ns", "timing", "LUT", "FF", "BRAM", "DSP", "power W", "Tj C", "gates", "Vivado", "wall s", "date"], d.builds.map(function (b) {
          return { cells: [b.id, num(b.wns_ns), num(b.whs_ns), b.timing_met ? "met" : b.timing_met === false ? "NOT MET" : "?", num(b.resources.lut), num(b.resources.ff), num(b.resources.bram_tile), num(b.resources.dsp), num(b.power_w), num(b.junction_c),
            b.gates_failing.length ? b.gates_failing.length + " failing" : "all " + b.gates_total + " pass", b.vivado_version || "?", num(b.wall_s), (b.source.date || "")], onclick: function () { openBuild(b); } };
        }), { num: [1, 2, 4, 5, 6, 7, 8, 9, 12] })]);
    }, function (e) { root.textContent = ""; add(root, [h("h1", null, "Latency and timing"), fail(e)]); });
  }
  function openStage(L, st) {
    openDrawer(st.id, [h("p", null, st.name), h("dl", null, h("dt", null, "domain"), h("dd", null, st.domain), h("dt", null, "kind"), h("dd", null, st.kind), h("dt", null, "adds"), h("dd", null, num(st.clocks) + " clocks, " + num(st.ns) + " ns"),
      h("dt", null, "removable"), h("dd", null, st.removable + " clock(s) by " + st.technique), h("dt", null, "post-route"), h("dd", null, st.netlist ? st.netlist.cells + " cells in " + st.netlist.clock + ", setup slack " + st.netlist.setup_slack_ns + " ns" : "not recorded")),
      h("h3", { class: "mt" }, "Why it exists"), h("p", null, st.why), h("h3", null, "Risk of removing it"), h("p", null, st.remove_risk), srcLine(L.sources.stages, "stage file")]);
  }
  function openBuild(b) {
    openDrawer(b.id, [h("dl", null, h("dt", null, "design"), h("dd", null, b.design || ""), h("dt", null, "build id"), h("dd", { class: "mono" }, b.build_id || "not recorded"), h("dt", null, "git commit"), h("dd", { class: "mono" }, b.git_commit || "not recorded"),
      h("dt", null, "Vivado"), h("dd", null, b.vivado_version || "not recorded"), h("dt", null, "clock period"), h("dd", null, num(b.period_ns) + " ns"), h("dt", null, "TNS"), h("dd", null, num(b.tns_ns)),
      h("dt", null, "failing endpoints"), h("dd", null, num(b.failing_endpoints)), h("dt", null, "power"), h("dd", null, num(b.power_w) + " W (" + (b.power_confidence || "confidence not recorded") + ", vectorless estimate)")),
      b.resources.available ? table(["resource", "used", "available"], Object.keys(b.resources.available).map(function (k) { return [k, num(b.resources[k]), num(b.resources.available[k])]; }), { num: [1, 2] }) : null,
      h("h3", { class: "mt" }, "Gates"), b.gates_failing.length ? h("ul", null, b.gates_failing.map(function (g) { return h("li", null, g); })) : h("p", null, "All " + b.gates_total + " gates pass."),
      srcLine(b.source, "digest"), b.run_source ? srcLine(b.run_source, "run record") : null]);
  }

  /* ---------- runs ---------- */
  function pageRuns() {
    var root = h("div", null, h("h1", null, "Runs"), loading()); main.textContent = ""; main.appendChild(root);
    api("/api/runs").then(function (d) {
      root.textContent = ""; add(root, h("h1", null, "Runs"));
      if (!d.runs.length) { add(root, h("p", null, "No run records in runs/. Start the navigator with --runs <dir> to read another run directory.")); return; }
      add(root, [h("p", { class: "mute" }, d.runs.length + " runs. Cost is the provider-reported figure, or, for Claude Code runs, the subscription plan's estimate: they are not the same kind of number."),
        table(["run", "design", "harness", "model", "stop reason", "cost", "wall s", "loops", "scope"], d.runs.map(function (r) {
          return { cells: [r.id, r.design || "", r.harness || "", r.model || "", r.stop || "finished", r.plan_cost_estimate_usd ? "plan est. $" + num(r.plan_cost_estimate_usd, 2) : r.cost_usd ? "$" + num(r.cost_usd, 2) : "not reported", num(r.wall_s, 0), num(r.loops), (r.scope || []).join(", ")], onclick: function () { openRun(r.id); } };
        }), { num: [6, 7] })]);
    }, function (e) { root.textContent = ""; add(root, [h("h1", null, "Runs"), fail(e)]); });
  }
  function openRun(id) {
    openDrawer(id, loading());
    api("/api/run?id=" + encodeURIComponent(id)).then(function (r) {
      var b = document.getElementById("drawer-body"); b.textContent = "";
      var sm = r.summary;
      add(b, [h("dl", null, Object.keys(sm).filter(function (k) { return typeof sm[k] !== "object"; }).map(function (k) { return [h("dt", null, k), h("dd", { class: "mono" }, String(sm[k]))]; })),
        r.scope ? [h("h3", { class: "mt" }, "Scope"), h("p", null, (r.scope.components || []).join(", ") + " (" + (r.scope.source || "") + ")")] : null,
        sm.gates_last ? [h("h3", { class: "mt" }, "Last gate result per stage"), h("p", null, Object.keys(sm.gates_last).map(function (k) { return k + ": " + (sm.gates_last[k] ? "pass" : "FAIL"); }).join("; "))] : null,
        r.usage.length ? [h("h3", { class: "mt" }, "Roles"), table(["stage", "role", "model", "turns", "tokens", "wall s", "ended"], r.usage.map(function (u) { return [u.stage, u.role, u.model || "", num(u.turns), num(u.tokens), num(u.wall_s, 0), u.ended || ""]; }), { num: [3, 4, 5] })] : null,
        r.calls.length ? [h("h3", { class: "mt" }, "Model calls (the resolver's log)"), table(["#", "purpose", "endpoint", "model", "in", "out", "cost"], r.calls.map(function (c) { return [num(c.seq), c.purpose, c.endpoint, c.model || "", num(c.prompt_tokens), num(c.completion_tokens), c.cost_usd === "unreported" ? "unreported" : c.cost_usd === null || c.cost_usd === undefined ? "-" : "$" + num(c.cost_usd, 4)]; }), { num: [0, 4, 5] })] : null,
        r.claude_code_calls.length ? [h("h3", { class: "mt" }, "Claude Code calls"), table(["call", "model", "turns", "wall s", "plan est. $"], r.claude_code_calls.map(function (c) { return [c.tag, (c.models_served || [c.model_requested]).join(", "), num(c.turns), num(c.wall_s, 0), num(c.plan_cost_estimate_usd, 3)]; }), { num: [2, 3, 4] })] : null,
        h("h3", { class: "mt" }, "Prompts: names and hashes"), r.fingerprints.length ? table(["call", "user message sha256", "chars", "system prompt sha256", "chars"], r.fingerprints.map(function (p) { return [p.call, p.user_fp ? short(p.user_fp.sha256, 16) : "-", p.user_fp ? num(p.user_fp.chars) : "", p.system_fp ? short(p.system_fp.sha256, 16) : "-", p.system_fp ? num(p.system_fp.chars) : ""]; }), { num: [2, 4] }) : h("p", { class: "mute" }, "This run recorded no prompt fingerprints (it is older than brief 99, or used another harness)."),
        h("p", { class: "mute" }, r.fp_note), srcLine(r.source, "summary")]);
    }, function (e) { var b = document.getElementById("drawer-body"); b.textContent = ""; add(b, fail(e)); });
  }

  /* ---------- measurements ---------- */
  function histo(hist, label, color) {
    var keys = Object.keys(hist || {}).map(Number).sort(function (a, b) { return a - b; });
    var W = 520, H = 170, pl = 38, pr = 8, pt = 8, pb = 34, mx = 0;
    keys.forEach(function (k) { mx = Math.max(mx, hist[k]); });
    var lo = keys[0], hi = keys[keys.length - 1], span = Math.max(1, hi - lo + 1);
    var bw = Math.max(2, (W - pl - pr) / Math.min(span, 400));
    var svg = s("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": label });
    [0, Math.ceil(mx / 2), mx].forEach(function (v) { var y = H - pb - (v / (mx || 1)) * (H - pb - pt); svg.appendChild(s("line", { x1: pl, x2: W - pr, y1: y, y2: y, class: "gr" })); svg.appendChild(s("text", { x: pl - 5, y: y + 4, "text-anchor": "end", class: "m" }, String(v))); });
    keys.forEach(function (k) { var x = pl + ((k - lo) / span) * (W - pl - pr), bh = (hist[k] / (mx || 1)) * (H - pb - pt);
      svg.appendChild(s("rect", { x: x, y: H - pb - bh, width: Math.max(2, bw - 1), height: bh, fill: "var(--fill)" }, s("title", null, k + " clocks: " + hist[k] + " restarts"))); });
    svg.appendChild(s("line", { x1: pl, x2: W - pr, y1: H - pb, y2: H - pb, class: "ax" }));
    svg.appendChild(s("text", { x: pl, y: H - 18, class: "m" }, lo)); svg.appendChild(s("text", { x: W - pr, y: H - 18, "text-anchor": "end", class: "m" }, hi));
    svg.appendChild(s("text", { x: (W + pl) / 2, y: H - 3, "text-anchor": "middle" }, label + " (clocks)"));
    return svg;
  }
  function stats(o) { return o ? h("p", { class: "mute" }, "n " + o.n + ", min " + o.min + ", median " + o.median + ", mean " + o.mean + ", max " + o.max + (o.min_ns !== undefined ? "; " + o.min_ns.toFixed(0) + " to " + o.max_ns.toFixed(0) + " ns" : "")) : null; }
  function lineChart(series, xKey, label, ylabel) {
    var W = 560, H = 230, pl = 44, pr = 12, pt = 10, pb = 36, xs = [], ys = [];
    Object.keys(series).forEach(function (n) { series[n].forEach(function (p) { xs.push(p[xKey]); ["min_clocks", "max_clocks", "mean_clocks"].forEach(function (k) { if (p[k] !== undefined) ys.push(p[k]); }); }); });
    if (!xs.length) return null;
    var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs), y0 = Math.floor(Math.min.apply(null, ys)) - 1, y1 = Math.ceil(Math.max.apply(null, ys)) + 1;
    var X = function (v) { return pl + (v - x0) / ((x1 - x0) || 1) * (W - pl - pr); }, Y = function (v) { return H - pb - (v - y0) / (y1 - y0) * (H - pb - pt); };
    var svg = s("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": label });
    for (var v = y0; v <= y1; v++) { svg.appendChild(s("line", { x1: pl, x2: W - pr, y1: Y(v), y2: Y(v), class: "gr" })); svg.appendChild(s("text", { x: pl - 5, y: Y(v) + 4, "text-anchor": "end", class: "m" }, v)); }
    Object.keys(series).forEach(function (n, i) {
      var d = series[n].map(function (p, j) { return (j ? "L" : "M") + X(p[xKey]) + " " + Y(p.mean_clocks); }).join("");
      svg.appendChild(s("path", { d: d, fill: "none", stroke: "var(--ink)", "stroke-width": 1.8, "stroke-dasharray": i ? "6 4" : null }));
      series[n].forEach(function (p) { svg.appendChild(s("line", { x1: X(p[xKey]), x2: X(p[xKey]), y1: Y(p.min_clocks), y2: Y(p.max_clocks), stroke: "var(--ink)", "stroke-width": 1 })); svg.appendChild(s("circle", { cx: X(p[xKey]), cy: Y(p.mean_clocks), r: 3, fill: i ? "var(--bg)" : "var(--ink)", stroke: "var(--ink)" }, s("title", null, n + " phase " + p[xKey] + " ps: min " + p.min_clocks + ", mean " + p.mean_clocks + ", max " + p.max_clocks))); });
      svg.appendChild(s("text", { x: pl + 8, y: pt + 12 + i * 14 }, (i ? "dashed: " : "solid: ") + n));
    });
    svg.appendChild(s("text", { x: (W + pl) / 2, y: H - 4, "text-anchor": "middle" }, label)); svg.appendChild(s("text", { x: 12, y: pt + 4, class: "m" }, ylabel));
    return svg;
  }
  function condRow(c) { return c ? [num(c.temp_c, 1), num(c.vccint_v, 3), num(c.vccaux_v, 3), num(c.vccbram_v, 3), c.inside_roc === undefined ? "not recorded" : c.inside_roc ? "inside" : "OUTSIDE"] : ["-", "-", "-", "-", "-"]; }
  function pageMeasure() {
    var root = h("div", null, h("h1", null, "Measurements"), loading()); main.textContent = ""; main.appendChild(root);
    Promise.all([api("/api/captures"), api("/api/measures")]).then(function (r) {
      var caps = r[0].captures, M = r[1], tabs = [["eye", "Eye and bathtub"], ["board", "Board sessions"], ["ppm", "Frequency offset"], ["buf", "Buffer latency"], ["cond", "Conditions"]];
      var body = h("div");
      function show() {
        body.textContent = "";
        if (state.measureTab === "eye") eyeTab(body, caps);
        else if (state.measureTab === "board") boardTab(body, M.board);
        else if (state.measureTab === "ppm") ppmTab(body, M.ppm);
        else if (state.measureTab === "buf") bufTab(body, M.rm_latency);
        else condTab(body, M, caps);
        Array.prototype.forEach.call(document.querySelectorAll("#mtabs button"), function (b) { b.setAttribute("aria-pressed", b.dataset.k === state.measureTab ? "true" : "false"); });
      }
      root.textContent = "";
      add(root, [h("h1", null, "Measurements"), h("p", { class: "mute" }, "These views draw committed records. None of them measures anything: a scan is a gated board tool run from the command line, and this page has no button for it."),
        h("div", { class: "tabs", id: "mtabs", role: "group", "aria-label": "Measurement views" }, tabs.map(function (t) { return h("button", { type: "button", "data-k": t[0], "aria-pressed": "false", on: { click: function () { state.measureTab = t[0]; show(); } } }, t[1]); })), body]);
      show();
    }, function (e) { root.textContent = ""; add(root, [h("h1", null, "Measurements"), fail(e)]); });
  }
  function eyeTab(body, caps) {
    if (!caps.length) { add(body, h("p", null, "No eye-scan captures (schema fda-capture-eye/1) under results/. Write one with python -m flow.eyescan run, or point the navigator at a directory with --captures.")); return; }
    if (!state.capA || !caps.some(function (c) { return c.id === state.capA; })) state.capA = caps[0].id;
    if (state.capB && !caps.some(function (c) { return c.id === state.capB; })) state.capB = null;
    var frame = h("iframe", { id: "eye", title: "Eye scan viewer", scrolling: "no", sandbox: "allow-scripts" });
    window.onmessage = function (e) { if (e.source === frame.contentWindow && e.data && typeof e.data.eyeHeight === "number") frame.style.height = Math.min(20000, e.data.eyeHeight + 8) + "px"; };
    function load() {
      var u = "/measure/page?a=" + encodeURIComponent(state.capA) + (state.capB ? "&b=" + encodeURIComponent(state.capB) : "") + "&theme=" + state.theme;
      frame.setAttribute("src", u);
      var any = caps.filter(function (c) { return c.id === state.capA || c.id === state.capB; }).some(function (c) { return c.synthetic; });
      synth.hidden = !any;
    }
    var opt = function (sel, empty) { return [empty ? h("option", { value: "" }, "none (one capture)") : null].concat(caps.map(function (c) { return h("option", { value: c.id, selected: c.id === sel }, (c.synthetic ? "SYNTHETIC: " : "") + (c.label || c.id) + "  " + (c.created || "").slice(0, 10)); })); };
    var synth = h("div", { class: "banner" }, h("strong", null, "SYNTHETIC. "), "A capture marked synthetic comes from an offline model (flow/eyescan/fake.py): it shows the view, not the link. Captures under results/b96d/hw are measured on the board; their state column says so.");
    add(body, [h("div", { class: "toolbar" },
        h("label", null, "Capture A ", h("select", { on: { change: function () { state.capA = this.value; load(); } } }, opt(state.capA, false))),
        h("label", null, "Capture B (compare) ", h("select", { on: { change: function () { state.capB = this.value || null; load(); } } }, opt(state.capB, true)))),
      synth,
      h("p", { class: "mute" }, "Choose a second capture to enable the viewer's Compare tab: side by side, bathtubs overlaid, and the difference. The 3-D tab rotates, and its two sliders cut the surface into the horizontal and vertical bathtubs."),
      frame,
      table(["capture", "state", "equaliser", "TX drive", "points", "width at target", "height at target", "4T clock phase", "scan complete", "source"], caps.map(function (c) { return { cells: [(c.synthetic ? "SYNTHETIC " : "") + (c.label || c.id), capState(c), c.equaliser || "", c.tx ? c.tx.diff + "/" + c.tx.pre + "/" + c.tx.post : "", num(c.points), capSize(c, "width_ui", "UI", 3), capSize(c, "height_mv", "mV nominal", 0), c.clk_phase_sel === null || c.clk_phase_sel === undefined ? "not recorded" : "sel " + c.clk_phase_sel, c.complete === null ? "grid size not recorded" : c.complete ? "yes" : "NO", c.source.file], onclick: function () { openRecordHead(c); } }; }), { num: [4] })]);
    load();
  }
  function capState(c) { return c.synthetic ? "SYNTHETIC (offline model)" : c.no_data ? "NO DATA (no samples were counted)" : "measured on the board"; }
  function capSize(c, k, unit, d) {
    var v = c[k], lo = c[k + "_lo"], hi = c[k + "_hi"];
    if (c.no_data) return "none: no data";
    if (v === null || v === undefined) { var sh = c.counts && c.counts.shallow; return sh ? "not resolved: " + sh + " points too shallow to vouch for the target depth" : "no open row or column"; }
    var rng = lo === null || lo === undefined || hi === null || hi === undefined ? "" : " (" + lo.toFixed(d) + " to " + hi.toFixed(d) + ")";
    return v.toFixed(d) + " " + unit + rng;
  }
  function openRecordHead(c) {
    openDrawer(c.label || c.id, [h("dl", null, h("dt", null, "synthetic"), h("dd", null, c.synthetic ? "yes: an offline model, not a measurement" : "no"), h("dt", null, "design"), h("dd", null, c.design || ""), h("dt", null, "board"), h("dd", null, c.board || ""),
      h("dt", null, "line rate"), h("dd", null, num(c.line_rate_gbps) + " Gb/s"), h("dt", null, "equaliser"), h("dd", null, c.equaliser), h("dt", null, "target BER"), h("dd", null, fmtBER(c.target_ber)), h("dt", null, "created"), h("dd", null, c.created || "")),
      h("p", { class: "mute" }, "The eye is measured by the receiver's own counters after the equaliser."), srcLine(c.source, "capture")]);
  }
  function boardTab(body, list) {
    if (!list.length) { add(body, h("p", null, "No board sessions recorded (results/*/hw/*/*/stage3.json).")); return; }
    var box = h("div");
    function draw() {
      var r = list[state.session] || list[0]; box.textContent = "";
      add(box, [h("p", null, h("strong", null, r.variant), " session ", r.session, ", ", r.restarts, " restarts, failed to lock: ", r.failed_to_lock, "; safety ", r.safety_ok ? "accepted" : "NOT accepted", "; link ", r.link_up ? "up" : "down"),
        h("div", { class: "grid2" },
          h("div", null, h("h3", null, "CDR and block lock time"), histo(r.lock_clocks && r.lock_clocks.histogram, "lock time", 1), stats(r.lock_clocks)),
          h("div", null, h("h3", null, "Echo E (minimum per link)"), histo(r.E_min && r.E_min.histogram, "E", 1), stats(r.E_min)),
          h("div", null, h("h3", null, "Loop L (minimum per link)"), histo(r.L_min && r.L_min.histogram, "L", 1), stats(r.L_min))),
        h("p", { class: "mute" }, "Each bar counts restarts of the link that gave that many clocks. E and L are the board's counters in core clocks (6.2 ns each); D from medians of minima: " + num(r.D_clocks) + " clocks; fibre one way " + num(r.fibre_one_way_ns, 2) + " ns."), srcLine(r.source, "record")]);
    }
    add(body, [h("div", { class: "toolbar" }, h("label", null, "Session ", h("select", { on: { change: function () { state.session = +this.value; draw(); } } }, list.map(function (r, i) { return h("option", { value: i, selected: i === state.session }, r.id + (r.started ? "  " + r.started.slice(0, 16) : "")); })))), box]);
    draw();
  }
  function ppmTab(body, P) {
    add(body, h("p", { class: "mute" }, "The board's frequency-offset sweep and the simulated partner's. A target the transmit phase interpolator could not reach is shown as not reachable: it is never a pass."));
    P.board.forEach(function (b) {
      add(body, [h("h2", null, "Board: " + b.id), table(["target ppm", "reachable", "calibrated ppm", "dwell ppm", "orders sent", "expected", "fired", "bad frames", "L min", "L max"], b.points.map(function (p) { return [num(p.target_ppm), p.reachable ? "yes" : "NO (not reached)", num(p.ppm_calibrated), num(p.ppm_dwell), num(p.orders_sent), num(p.orders_expected), num(p.orders_fired), num(p.frames_bad), num(p.l_min), num(p.l_max)]; }), { num: [0, 2, 3, 4, 5, 6, 7, 8, 9] }), srcLine(b.source, "record")]);
    });
    P.simulated.forEach(function (sm) {
      add(body, [h("h2", null, "Simulated partner: " + sm.id), table(["ppm", "frames sent", "frames received", "good", "bad", "idle inserts", "idle deletes", "overflow"], sm.points.map(function (p) { return [num(p.ppm), num(p.frames_sent), num(p.frames), num(p.good), num(p.bad), num(p.inserts), num(p.deletes), num(p.overflow)]; }), { num: [0, 1, 2, 3, 4, 5, 6, 7] }), srcLine(sm.source, "record")]);
    });
    if (!P.board.length && !P.simulated.length) add(body, h("p", null, "No frequency-offset records found."));
  }
  function bufTab(body, list) {
    if (!list.length) { add(body, h("p", null, "No buffer-latency records (results/*/rm_latency_sim.json).")); return; }
    list.forEach(function (r) {
      add(body, [h("h2", null, "Rate-match buffer latency by clock phase"), h("p", { class: "mute" }, r.what), lineChart(r.series, "phase_ps", "phase between the clocks (ps)", "clocks in the buffer: mean, with min to max"), h("p", { class: "mute" }, "Simulation, not the board. " + (r.phase_ps_is || "")), srcLine(r.source, "record")]);
    });
  }
  function condTab(body, M, caps) {
    var rows = [];
    M.board.forEach(function (b) { rows.push([b.id + " start"].concat(condRow(b.conditions_start))); rows.push([b.id + " end"].concat(condRow(b.conditions_end))); });
    M.ppm.board.forEach(function (b) { rows.push([b.id + " sweep start"].concat(condRow(b.conditions_start))); rows.push([b.id + " sweep end"].concat(condRow(b.conditions_end))); });
    caps.forEach(function (c) { var k = c.conditions || {}; rows.push([(c.synthetic ? "SYNTHETIC " : "") + c.id + " start"].concat(condRow(k.start))); rows.push([(c.synthetic ? "SYNTHETIC " : "") + c.id + " end"].concat(condRow(k.end))); });
    add(body, [h("p", { class: "mute" }, "Die temperature and supply rails read from the XADC or SYSMON at the start and end of each run, with whether they were inside the recommended operating conditions. Only these two samples are recorded, so there is no timeline to draw; a failure report would show the samples nearest to it."),
      rows.length ? table(["record", "Tj C", "VCCINT V", "VCCAUX V", "VCCBRAM V", "ROC"], rows, { num: [1, 2, 3, 4] }) : h("p", null, "No conditions recorded.")]);
  }

  /* ---------- health ---------- */
  function pageHealth() {
    var root = h("div", null, h("h1", null, "Health"), loading()); main.textContent = ""; main.appendChild(root);
    api("/api/health").then(function (d) {
      root.textContent = ""; add(root, h("h1", null, "Health"));
      var order = { fail: 0, warn: 1, unknown: 2, "not-run": 3, ok: 4 };
      add(root, [h("div", { class: "toolbar" }, h("span", null, Object.keys(d.counts).sort(function (a, b) { return order[a] - order[b]; }).map(function (k) { return d.counts[k] + " " + k; }).join(", ")), h("span", { class: "mute" }, "checked " + d.checked_at), h("button", { type: "button", on: { click: pageHealth } }, "Re-check")),
        h("p", { class: "mute" }, d.note)]);
      d.groups.forEach(function (g) {
        add(root, h("h2", null, g));
        d.checks.filter(function (c) { return c.group === g; }).forEach(function (c) { add(root, healthRow(c)); });
      });
    }, function (e) { root.textContent = ""; add(root, [h("h1", null, "Health"), fail(e)]); });
  }
  function healthRow(c) {
    var btn = null, extra = null;
    var actionName = c.action || (c.id === "usage" ? "usage_live" : null);
    var labels = { usage_live: "Run the usage check now", llm_probe: "Probe endpoints", ci_main: "Ask GitHub" };
    var costs = { usage_live: "0 tokens", llm_probe: "spends a few tokens", ci_main: "one GitHub API call" };
    if (actionName) btn = h("button", { type: "button", title: costs[actionName], on: { click: function (e) { var b = e.target; b.disabled = true; b.textContent = "Running"; post("/api/action/" + actionName).then(function () { pageHealth(); }, function () { b.disabled = false; b.textContent = "Failed: retry"; }); } } }, labels[actionName]);
    if (c.output) extra = h("pre", { class: "cmd" }, c.output.join("\n"));
    return h("div", { class: "health-row" }, stat(c.status), h("div", null, h("strong", null, c.title), h("div", null, c.detail), h("div", { class: "how" }, "How: " + c.how + ". Checked " + c.checked_at + "."), extra),
      h("div", { class: "act" }, btn, btn ? h("div", { class: "how" }, costs[actionName]) : null));
  }

  /* ---------- models ---------- */
  function pageModels() {
    var root = h("div", null, h("h1", null, "Models"), loading()); main.textContent = ""; main.appendChild(root);
    api("/api/models").then(function (d) {
      root.textContent = "";
      if (d.error) { add(root, [h("h1", null, "Models"), h("div", { class: "banner" }, d.error)]); return; }
      add(root, [h("h1", null, "Models"), h("p", { class: "mute" }, "The model table the agent resolves today (brief 108): which endpoint and model each purpose uses, and which layer set it. Only whether a key is present is checked; no endpoint is called."),
        h("p", { class: "mute" }, "table hash ", h("code", null, d.hash), "; layers: " + (d.layers.length ? d.layers.map(function (l) { return l.layer + " (" + (l.source || "") + ")"; }).join(", ") : "built in only") + "; resolved " + d.checked_at),
        table(["purpose", "endpoint", "kind", "model", "options", "set by", "key"], d.table.map(function (r) { return { cells: [r.name, r.endpoint, r.kind, r.model || "(off)", Object.keys(r.options).map(function (k) { return k + "=" + r.options[k]; }).join(" "), r.from, r.key_state], onclick: function () { openModel(r); } }; })),
        h("p", { class: "src" }, "how: " + d.how)]);
    }, function (e) { root.textContent = ""; add(root, [h("h1", null, "Models"), fail(e)]); });
  }
  function openModel(r) {
    openDrawer(r.name, h("dl", null, h("dt", null, "endpoint"), h("dd", null, r.endpoint + " (" + r.kind + ")"), h("dt", null, "model"), h("dd", { class: "mono" }, r.model || "(off: no model configured)"), h("dt", null, "set by"), h("dd", null, r.from),
      h("dt", null, "key variable"), h("dd", { class: "mono" }, r.key_env || "none"), h("dt", null, "key"), h("dd", null, r.key_state), h("dt", null, "options"), h("dd", { class: "mono" }, JSON.stringify(r.options)), r.note ? [h("dt", null, "note"), h("dd", null, r.note)] : null));
  }


  /* ---------- live progress ---------- */
  function usd(x) { return x === null || x === undefined ? "n/a" : "$" + Number(x).toFixed(2); }
  function age(sec) { return sec === null || sec === undefined ? "no file yet" : sec < 90 ? sec + " s ago" : sec < 5400 ? Math.round(sec / 60) + " min ago" : (sec / 3600).toFixed(1) + " h ago"; }
  function stageTrack(p) {
    var W = 1000, n = p.stages.length, bw = W / n;
    var svg = s("svg", { viewBox: "0 0 " + W + " 74", role: "img", "aria-label": "Stage track: current stage " + (p.stage || "none") });
    p.stages.forEach(function (name, i) {
      var done = p.stages_done.some(function (d) { return d.stage === name; }), cur = p.stage === name && p.status !== "finished";
      var v = p.visits[name] || 0;
      svg.appendChild(s("g", null, s("title", null, name + ": " + (done ? "finished" : cur ? "in progress" : v ? "visited" : "not reached") + (v ? ", visit " + v : "")),
        s("rect", { x: i * bw + 2, y: 4, width: bw - 4, height: 34, fill: done ? "var(--fill)" : cur ? "var(--fill2)" : "var(--bg)", stroke: cur ? "var(--ink)" : "var(--rule2)", "stroke-width": cur ? 3 : 1, "stroke-dasharray": !done && !cur && !v ? "4 3" : null }),
        s("text", { x: i * bw + bw / 2, y: 26, "text-anchor": "middle", fill: done ? "var(--on-fill)" : "var(--ink)", style: null }, String(i)),
        s("text", { x: i * bw + bw / 2, y: 56, "text-anchor": "middle", class: "m" }, name.length > 13 ? name.slice(0, 12) + "." : name),
        s("text", { x: i * bw + bw / 2, y: 70, "text-anchor": "middle", class: "m" }, v ? "visit " + v : "")));
    });
    return svg;
  }
  function costBar(c) {
    var b = c.budget_usd || 0, frac = b ? Math.min(1, c.reported_usd / b) : 0;
    return s("svg", { viewBox: "0 0 400 22", role: "img", "aria-label": "Provider-reported cost " + usd(c.reported_usd) + " of budget " + usd(c.budget_usd), class: "bar" },
      s("rect", { x: 0.5, y: 4.5, width: 399, height: 14, fill: "none", stroke: "var(--rule2)" }), s("rect", { x: 1, y: 5, width: 398 * frac, height: 13, fill: frac > 0.8 ? "var(--ink)" : "var(--fill2)" }));
  }
  function runDetail(p) {
    var c = p.cost;
    return h("div", null,
      h("div", { class: "kpi" },
        h("div", null, h("b", null, h("span", { class: "st " + (p.status === "active" ? "ok" : p.status === "finished" ? "unknown" : "warn") }, p.status.toUpperCase())), "last file write " + age(p.last_write_age_s)),
        h("div", null, h("b", null, p.stage || "none yet"), "stage" + (p.visit ? ", visit " + p.visit : "") + (p.role ? ", role " + p.role : "")),
        h("div", null, h("b", null, usd(c.reported_usd)), "provider-reported" + (c.budget_usd ? " of " + usd(c.budget_usd) : "")),
        h("div", null, h("b", null, usd(c.plan_estimate_usd)), "plan estimate (Claude Code)"),
        h("div", null, h("b", null, String(p.tokens)), "tokens")),
      p.stop ? h("p", { class: "banner" }, "Stop reason: " + p.stop) : null,
      stageTrack(p), costBar(c), h("p", { class: "mute" }, c.note + (c.reported_calls_without_cost ? " " + c.reported_calls_without_cost + " model calls report no cost." : "")),
      h("h3", { class: "mt2" }, "Gate results"),
      p.gates.length ? table(["stage", "design", "build", "verdict", "numbers", "failing"], p.gates.slice().reverse().map(function (g) {
        return [g.stage || "", g.design, g.variant, stat(g.verdict === "PASS" ? "ok" : "fail"), g.numbers, g.failing.join("; ") || (Object.keys(g.stages).length ? "none" : "")]; })) : h("p", { class: "mute" }, "No gates call yet."),
      h("h3", { class: "mt2" }, "Audit log, last " + p.audit_tail.length + " of " + p.audit_rows),
      p.audit_tail.length ? table(["tool", "stage", "ok", "result"], p.audit_tail.slice().reverse().map(function (a) { return [a.tool, a.stage || "", a.refused ? "refused" : a.ok === null ? "" : a.ok ? "ok" : "failed", a.line]; })) : h("p", { class: "mute" }, "The audit log has no rows yet."),
      h("p", { class: "src" }, "read from " + p.source.dir + " (" + p.source.files.join(", ") + "); nothing is written"));
  }
  function pageLive() {
    var root = h("div", null, h("h1", null, "Live"), loading()), sel = state.liveRun || null, detail = h("div", { "aria-live": "polite" });
    main.textContent = ""; main.appendChild(root);
    function loadDetail() {
      if (!sel) { detail.textContent = ""; return; }
      api("/api/live/run?id=" + encodeURIComponent(sel)).then(function (p) { detail.textContent = ""; add(detail, [h("h2", null, p.id + (p.name ? "  " + p.name : "")), runDetail(p)]); }, function (e) { detail.textContent = ""; add(detail, fail(e)); });
    }
    function load() {
      api("/api/live").then(function (d) {
        var list = h("div", null);
        add(list, [h("p", { class: "mute" }, "Every run directory in " + d.dir + ", whoever started it (this page or the command line). A run counts as working while one of its log files was written in the last 3 minutes; otherwise it is idle (finished, paused for an answer, stopped or crashed: the summary file says which). Refreshes every 5 s."),
          d.started.length ? [h("h2", null, "Started from this page"), table(["id", "status", "target", "run", "started", ""], d.started.map(function (r) {
            var b = r.status === "running" ? h("button", { type: "button", on: { click: function () { if (confirm("Stop " + r.id + "? Its process group gets SIGTERM, then SIGKILL after 20 s.")) post("/api/run/stop", { id: r.id }).then(function (j) { alert(j.stopped ? j.note : j.refused); load(); }); } } }, "Stop") : r.slot && r.slot.released === false ? "slot not released: check Health" : "";
            return { cells: [r.id, r.status + (r.exit_code !== null && r.exit_code !== undefined ? " (exit " + r.exit_code + ")" : ""), (r.summary || {}).target || "", r.run_id || "not found yet", r.started, b], onclick: r.run_id ? function () { sel = state.liveRun = r.run_id; loadDetail(); } : null };
          }))] : null,
          h("h2", null, "Runs"),
          d.runs.length ? table(["run", "design", "status", "stage", "visit", "cost", "budget", "last write"], d.runs.map(function (r) {
            return { cells: [r.id, r.name || "", stat(r.status === "active" ? "ok" : r.status === "finished" ? "unknown" : "warn"), r.stage || "", r.visit === null ? "" : String(r.visit), usd(r.cost.reported_usd), usd(r.cost.budget_usd), age(r.last_write_age_s)], onclick: function () { sel = state.liveRun = r.id; loadDetail(); } };
          }), { num: [4] }) : h("p", null, "No run directories yet."), h("p", { class: "mute" }, "Click a run for its stages, gates and audit log.")]);
        root.textContent = ""; add(root, [h("h1", null, "Live"), list, detail]); loadDetail();
      }, function (e) { root.textContent = ""; add(root, [h("h1", null, "Live"), fail(e)]); });
    }
    load();
    every(5000, function () { if (!document.hidden) load(); });
  }

  /* ---------- start a run ---------- */
  function pageStart() {
    var root = h("div", null, h("h1", null, "Start"), loading()); main.textContent = ""; main.appendChild(root);
    api("/api/start/options").then(function (o) {
      var f = state.start = state.start || { kind: "task", harness: "claude_code", effort: "medium", usd: o.default_usd, arms: ["H1"], components: [], request: "" };
      var out = h("div", { class: "panel", "aria-live": "polite" });
      function sel(label, opts, cur, on) { return h("label", null, label + " ", h("select", { on: { change: function () { on(this.value); } } }, opts.map(function (x) { return h("option", { value: x, selected: x === cur }, x); }))); }
      function render() {
        var models = o.models[f.harness] || [];
        if (models.indexOf(f.model) < 0) f.model = models[0] || "";
        var fields = [sel("Kind", ["task", "project"], f.kind, function (v) { f.kind = v; render(); })];
        if (f.kind === "task") {
          if (!f.task) f.task = o.tasks[0];
          if (!f.board) f.board = o.boards.indexOf("nexys_a7_100t") >= 0 ? "nexys_a7_100t" : o.boards[0];
          fields.push(sel("Task", o.tasks, f.task, function (v) { f.task = v; }), sel("Board", o.boards, f.board, function (v) { f.board = v; }),
            h("fieldset", null, h("legend", null, "Harness arms (none ticked = the A0 baseline)"), o.arms.map(function (a) { return h("label", { class: "inl" }, h("input", { type: "checkbox", checked: f.arms.indexOf(a) >= 0, on: { change: function () { var i = f.arms.indexOf(a); if (this.checked && i < 0) f.arms.push(a); if (!this.checked && i >= 0) f.arms.splice(i, 1); } } }), a); }), h("p", { class: "mute" }, o.arm_note)));
        } else {
          var names = o.projects.map(function (p) { return p.name; });
          if (!f.project) f.project = names[0];
          var cl = o.owned_components[f.project] || [];
          fields.push(sel("Managed project", names, f.project, function (v) { f.project = v; f.components = []; render(); }),
            h("fieldset", null, h("legend", null, "Components the request may touch (none ticked: the agent resolves the scope from the request)"), cl.map(function (c) { return h("label", { class: "inl" }, h("input", { type: "checkbox", checked: f.components.indexOf(c.name) >= 0, on: { change: function () { var i = f.components.indexOf(c.name); if (this.checked && i < 0) f.components.push(c.name); if (!this.checked && i >= 0) f.components.splice(i, 1); } } }), c.name); })),
            h("label", null, "Change request ", h("input", { type: "text", class: "fullw", value: f.request, maxlength: 400, on: { input: function () { f.request = this.value; } } })));
        }
        fields.push(sel("Harness", ["claude_code", "deepagents"], f.harness, function (v) { f.harness = v; render(); }), sel("Model (from the resolved table)", models, f.model, function (v) { f.model = v; }),
          sel("Effort", o.efforts, f.effort, function (v) { f.effort = v; }),
          h("label", null, "Budget (USD, at most " + o.max_usd + ") ", h("input", { type: "number", min: "0.1", max: String(o.max_usd), step: "0.1", value: String(f.usd), on: { input: function () { f.usd = parseFloat(this.value); } } })));
        var go = h("button", { type: "button", on: { click: function () {
          var body = { kind: f.kind, harness: f.harness, model: f.model, effort: f.effort, max_usd: f.usd, confirm: "start" };
          if (f.kind === "task") { body.task = f.task; body.board = f.board; body.arms = f.arms; } else { body.project = f.project; body.components = f.components; body.request = f.request; }
          if (!confirm("Start this run? It spends up to $" + f.usd + " (provider-reported), takes a heavy slot, and runs until it ends or you stop it.")) return;
          go.disabled = true; out.textContent = "Starting";
          post("/api/run/start", body).then(function (j) { out.textContent = ""; go.disabled = false;
            if (j.started) { add(out, [h("h3", null, "Started " + j.id), h("p", null, "process " + j.record.pid + ", slot job: " + (j.record.slot.job || "")), h("p", null, h("a", { href: "#/live" }, "Watch it on the Live page"))]); }
            else add(out, h("div", { class: "banner" }, h("strong", null, "Refused: nothing was started. "), j.refused)); }, function (e) { go.disabled = false; out.textContent = ""; add(out, fail(e)); });
        } } }, "Start the run");
        form.textContent = ""; add(form, [h("div", { class: "formgrid" }, fields), go]);
      }
      var form = h("div", null);
      var u = o.usage;
      root.textContent = "";
      add(root, [h("h1", null, "Start"),
        h("p", { class: "mute" }, "Starts the agent's own command line with the same guards, then shows it on the Live page. " + o.never + "."),
        h("div", { class: "kpi" }, h("div", null, h("b", null, u.percent === undefined ? "unknown" : u.percent + "%"), "weekly usage (stop at " + o.usage_stop_pct + "%)"), h("div", null, h("b", null, String(o.started.filter(function (r) { return r.status === "running"; }).length)), "navigator runs going (limit " + o.active_limit + ")"),
          o.slots.map(function (l) { return h("div", null, h("b", null, l.status === "ok" ? "free" : "held"), l.title); })),
        h("ul", null, o.guards.map(function (g) { return h("li", null, g); })),
        form, out]);
      render();
    }, function (e) { root.textContent = ""; add(root, [h("h1", null, "Start"), fail(e)]); });
  }

  /* ---------- board (locked, read-only) ---------- */
  function pageBoard() {
    var root = h("div", null, h("h1", null, "Board"), loading()); main.textContent = ""; main.appendChild(root);
    api("/api/board").then(function (d) {
      root.textContent = "";
      add(root, [h("h1", null, "Board"), h("p", { class: "mute" }, "Read-only actions on a board attached to this PC. Each one takes board.lock and a heavy slot, reads, and releases both. None of them programs a device, writes a register, sets a hardware property, or touches the laser, the flash or the eFUSE."),
        h("div", { class: "kpi" }, h("div", null, h("b", null, d.lock.held ? "held" : "free"), "board.lock" + (d.lock.held ? ": " + d.lock.held_by : ""))),
        d.boards.length ? d.boards.map(function (b) {
          var res = h("div", { "aria-live": "polite" });
          var btns = b.actions.map(function (a) { return h("button", { type: "button", title: "takes board.lock and a heavy slot; a Vivado session of up to a minute", on: { click: function (ev) {
            var bt = ev.target; if (!confirm("Run '" + d.titles[a] + "' on " + b.board + "? It takes board.lock and a heavy slot, starts hw_server and Vivado's hardware manager, reads, and releases both.")) return;
            bt.disabled = true; res.textContent = "Running: this starts Vivado and can take a minute";
            post("/api/board/run", { board: b.board, action: a, confirm: "read" }).then(function (j) { bt.disabled = false; res.textContent = ""; add(res, boardResult(j)); }, function (e) { bt.disabled = false; res.textContent = ""; add(res, fail(e)); }); } } }, d.titles[a]); });
          return h("div", { class: "panel mt" }, h("h2", null, b.board), h("p", { class: "mute" }, [b.part, b.device, b.power ? b.power + " power" : null, b.cable ? "cable " + b.cable : null, b.profile ? "register profile: " + b.profile : "no register profile (targets and SYSMON only)"].filter(Boolean).join(", ")),
            b.note ? h("p", { class: "banner" }, b.note) : null, h("div", { class: "toolbar" }, btns), b.last ? h("p", { class: "src" }, "last: " + b.last.action + " at " + b.last.checked_at + (b.last.ok ? "" : " (did not complete)")) : null, res);
        }) : h("p", null, "boards.yaml lists no board. Run flow/hw_discover.py."),
        h("ul", { class: "mute" }, d.rules.map(function (r) { return h("li", null, r); }))]);
    }, function (e) { root.textContent = ""; add(root, [h("h1", null, "Board"), fail(e)]); });
  }
  function boardResult(j) {
    if (j.refused) return h("div", { class: "banner" }, h("strong", null, "Refused: nothing ran. "), j.refused);
    var out = [h("h3", null, j.title + ": " + (j.ok ? "done" : "did not complete")), j.error ? h("div", { class: "banner" }, j.error) : null,
      (j.section_errors || []).map(function (e) { return h("p", { class: "banner" }, e.section + ": " + e.what); })];
    if (j.targets) out.push(h("h3", { class: "mt" }, "JTAG targets" + (j.targets_complete ? "" : " (list incomplete)")), j.targets.length ? table(["cable", "this board", "devices", "error"], j.targets.map(function (t) { return [t.uid, t.mine ? "yes" : "", t.devices.map(function (d) { return d.device + " " + d.part + " " + d.idcode; }).join("; "), t.error || ""]; })) : h("p", null, "none seen"));
    if (j.sysmon) out.push(h("h3", { class: "mt" }, "SYSMON: " + j.sysmon.verdict), j.sysmon.channels.length ? table(["channel", "value", "min", "max", "inside"], j.sysmon.channels.map(function (c) { return [c.name, String(c.value), c.min === null ? "" : String(c.min), c.max === null ? "" : String(c.max), c.inside ? "yes" : "NO"]; }), { num: [1, 2, 3] }) : null,
      h("p", { class: "src" }, "limits: " + j.sysmon.roc_source + ". " + j.sysmon.caveat));
    if (j.design && Object.keys(j.design).length) out.push(h("h3", { class: "mt" }, "Loaded design"), h("dl", null, Object.keys(j.design).filter(function (k) { return typeof j.design[k] === "string"; }).map(function (k) { return [h("dt", null, k), h("dd", { class: "mono" }, j.design[k])]; }),
      j.design.features_set ? [h("dt", null, "FEATURES set"), h("dd", null, j.design.features_set.join(", "))] : null));
    if (j.link && j.link.bits) out.push(h("h3", { class: "mt" }, "Link: " + (j.link.link_up ? "up" : "not up")), table(["signal", "bit"], Object.keys(j.link.bits).map(function (k) { return [k, String(j.link.bits[k])]; })), h("p", { class: "src" }, j.link.note));
    out.push(h("p", { class: "src" }, "locks: " + (j.locks ? "board.lock released " + (j.locks.released ? j.locks.released.board_lock : "") + ", heavy slot released " + (j.locks.released ? j.locks.released.slot : "") : "") + "; " + (j.seconds || 0) + " s"));
    return out;
  }

  /* ---------- traceability (brief 116) ---------- */
  var TRACE_METHODS = [["sim_test", "sim test"], ["uvm_test", "UVM"], ["assertion", "SVA"], ["formal", "formal"], ["coverage_bin", "coverage"], ["timing", "timing"], ["sim_measurement", "sim measure"], ["board_measurement", "board"], ["review", "review"]];
  var TRACE_STATE = { verified: "verified", fail: "FAILS", not_run: "not run", stale: "stale", bounded: "bounded only", no_measurement: "no measurement" };
  function traceState(r) {
    var t = TRACE_STATE[r.state] || r.state;
    if (r.state === "verified" && r.external && !r.hardware_verified) return "passes without hardware; hardware open";
    if (r.state === "verified" && r.kind === "performance") t += " (" + (r.basis === "board" ? "board-measured" : r.basis === "timing" ? "post-route timing" : "simulation only") + ")";
    if (r.state === "verified" && r.stale_items) t += "; " + r.stale_items + " item(s) stale";
    return t;
  }
  function pageTrace() {
    var root = h("div", null, h("h1", null, "Traceability"), loading()); main.textContent = ""; main.appendChild(root);
    api("/api/trace").then(function (d) {
      root.textContent = "";
      if (d.error) { add(root, [h("h1", null, "Traceability"), h("div", { class: "banner" }, d.error)]); return; }
      add(root, [h("h1", null, "Traceability"), h("p", { class: "mute" }, d.framing),
        h("p", { class: "src" }, "how: python -m flow.trace_v1 show <design>. Status is computed from the evidence files, never typed.")]);
      d.designs.forEach(function (g) {
        var byId = {}; g.items.forEach(function (i) { byId[i.id] = i; });
        var rows = g.requirements.map(function (r) {
          var cells = [h("span", null, h("b", null, r.id + " "), r.title), r.kind, h("span", { class: r.state === "verified" ? "" : "mute" }, traceState(r))];
          TRACE_METHODS.forEach(function (m) {
            var its = r.items.filter(function (id) { return byId[id].method === m[0]; }).map(function (id) { return byId[id]; });
            cells.push(its.length ? its.map(function (i) { return h("div", null, i.status.replace("_", " ") + (i.instrument ? " [" + i.instrument + "]" : "")); }) : "");
          });
          return { cells: cells, onclick: function () { openRequirement(r, byId); } };
        });
        add(root, [h("div", { class: "panel mt" }, h("h2", null, g.design), h("p", null, g.summary.line),
          table(["requirement", "kind", "state"].concat(TRACE_METHODS.map(function (m) { return m[1]; })), rows, {}),
          h("h3", { class: "mt" }, "Gaps (" + g.gaps.length + ")"),
          g.gaps.length ? h("ul", null, g.gaps.map(function (x) { return h("li", null, h("code", null, x.id), " " + x.type.replace(/_/g, " ") + ": " + x.text); })) : h("p", null, "None."))]);
      });
    }, function (e) { root.textContent = ""; add(root, [h("h1", null, "Traceability"), fail(e)]); });
  }
  function openRequirement(r, byId) {
    var pf = r.performance;
    openDrawer(r.id, [h("p", null, r.title), r.text ? h("p", null, r.text) : null,
      h("dl", null, h("dt", null, "kind"), h("dd", null, r.kind), h("dt", null, "state"), h("dd", null, traceState(r)), h("dt", null, "specification status"), h("dd", null, r.spec_status || "unspecified"),
        r.source ? [h("dt", null, "source"), h("dd", { class: "mono" }, r.source)] : null,
        pf ? [h("dt", null, "bound"), h("dd", null, pf.quantity + " " + pf.op + " " + pf.bound + " " + pf.unit + "; " + pf.condition)] : null,
        r.external ? [h("dt", null, "external element"), h("dd", null, r.external + "; hardware verification " + r.hardware_closure)] : null),
      h("h3", null, "Evidence"),
      table(["item", "method", "status", "result", "evidence"], r.items.map(function (id) {
        var i = byId[id];
        return [i.title || i.id, i.method + (i.instrument ? " / " + i.instrument : ""), i.status.replace("_", " "), i.detail + (i.stale_because ? " (" + i.stale_because + ")" : ""),
          i.evidence && i.evidence.exists ? h("button", { type: "button", class: "name", on: { click: function () { openRecord(i.evidence.file); } } }, i.evidence.file) : "none"];
      }), {})]);
  }

  /* ---------- router ---------- */
  var ROUTES = { project: pageProject, timing: pageTiming, runs: pageRuns, live: pageLive, start: pageStart, board: pageBoard, measure: pageMeasure, trace: pageTrace, health: pageHealth, models: pageModels };
  function route() {
    var k = (location.hash || "#/project").replace(/^#\//, "");
    if (!ROUTES[k]) k = "project";
    closeDrawer(); clearTimers();
    var nav = document.getElementById("nav"); nav.textContent = "";
    PAGES.forEach(function (p) { nav.appendChild(h("a", { href: "#/" + p[0], "aria-current": p[0] === k ? "page" : null }, p[1])); });
    ROUTES[k]();
  }
  document.getElementById("theme").addEventListener("click", function () {
    state.theme = state.theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", state.theme); this.textContent = state.theme === "dark" ? "Light" : "Dark";
    var f = document.getElementById("eye"); if (f && f.getAttribute("src")) f.setAttribute("src", f.getAttribute("src").replace(/theme=\w+/, "theme=" + state.theme));
  });
  window.addEventListener("hashchange", route);
  api("/api/overview").then(function (o) {
    document.getElementById("meta").textContent = o.repo + " " + o.branch + " " + (o.commit || "") + "  bound to " + o.binds;
  }, function () {});
  route();
})();
