"""Brief 222: the Navigator's permission settings panel (its API and storage), the permission question on the Live page, the mode a started run is given, and the
board gate. No model, no process and no board: the fakes of the stage 2 tests stand in."""

from __future__ import annotations

import json
import re

import pytest
import yaml

from agent.core import permissions as P
from navigator import summary as NS
from navigator.tests.test_103_navigator import ROOT
from navigator.tests.test_103s2_navigator import PROJ, TASK, TOKEN, env, make_rc, web  # noqa: F401  (env and web are fixtures)

NAMES = {a.name for a in P.ACTIONS}


def args_of(sp, flag):
    a = sp.calls[0]["argv"]
    return [a[i + 1] for i, x in enumerate(a) if x == flag]


# --- the mode a started run is given ---------------------------------------------------------------------------------------------------

def test_a_run_started_with_nothing_saved_gets_the_navigators_default_ask(env):
    rc, _, sp = make_rc(env)
    r = rc.start(dict(TASK))
    assert r["started"], r
    assert args_of(sp, "--permissions") == ["ask"] and args_of(sp, "--ask-above-usd") == ["1"]
    s = r["record"]["summary"]["permissions"]
    assert s["mode"] == "ask" and "Navigator's default" in s["source"]


def test_saved_settings_for_the_project_become_flags_on_the_command(env, tmp_path):
    rc, _, sp = make_rc(env)
    rc.perm_file = tmp_path / "perm.yaml"
    P.save_config("c10_dds_sine", "auto", {"run_vivado": "deny", "read_board": "ask", "run_simulation": "allow"}, 2.5, rc.perm_file)
    r = rc.start(dict(TASK))
    assert r["started"], r
    assert args_of(sp, "--permissions") == ["auto"] and args_of(sp, "--deny") == ["run_vivado"] and args_of(sp, "--ask") == ["read_board"] and args_of(sp, "--ask-above-usd") == ["2.5"]
    assert args_of(sp, "--allow") == []                                                  # run_simulation is the mode's own value: not passed
    assert r["record"]["summary"]["permissions"]["overrides"] == {"run_vivado": "deny", "read_board": "ask"}
    rc2, _, sp2 = make_rc(env)
    rc2.perm_file = rc.perm_file
    rc2.runs_dir = rc.runs_dir
    r2 = rc2.start({**TASK, "task": "c10_dds_sine", "permissions": {"mode": "plan"}})         # a choice on the Start page wins for this run only
    assert r2["started"] is False or args_of(sp2, "--permissions") == ["plan"]


def test_a_mode_chosen_on_the_start_page_is_passed_and_checked(env):
    rc, _, sp = make_rc(env)
    r = rc.start({**TASK, "permissions": {"mode": "plan", "overrides": {"run_vivado": "allow"}}})
    assert r["started"], r
    assert args_of(sp, "--permissions") == ["plan"] and args_of(sp, "--allow") == ["run_vivado"]


@pytest.mark.parametrize("perm,word", [({"mode": "yolo"}, "mode"), ({"mode": "ask", "overrides": {"flash_it": "allow"}}, "override"), ({"mode": "ask", "overrides": {"run_vivado": "maybe"}}, "override"),
                                       ({"mode": "ask", "extra": 1}, "object"), ({"mode": "ask", "ask_above_usd": 999}, "ask-above"), ("ask", "object")])
def test_a_bad_permission_choice_is_refused_before_anything_starts(env, perm, word):
    rc, _, sp = make_rc(env)
    r = rc.start({**TASK, "permissions": perm})
    assert r["started"] is False and word in r["refused"] and not sp.calls


def test_a_project_resume_carries_the_mode_too(env):
    rc, _, sp = make_rc(env)
    r = rc.start({**PROJ, "permissions": {"mode": "auto"}})
    assert r["started"], r
    assert args_of(sp, "--permissions") == ["auto"] and sp.calls[0]["argv"][3] == "resume"


# --- the permission question on the Live page ---------------------------------------------------------------------------------------------

def paused(runs, rid="20261120-100000-abcd", kind="permission"):
    rd = runs / rid
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "config.json").write_text(json.dumps({"name": "t1", "run_limits": {"usd": 3.0}, "harness": "claude_code"}))
    (rd / "pending.json").write_text(json.dumps({"paused": {"kind": kind, "stage": 3, "stage_name": "constraints", "mode": "ask", "needs": ["run_vivado"],
                                                            "actions": [{"action": "run_vivado", "label": "Run Vivado synthesis and implementation", "plain": "Run Vivado builds."}],
                                                            "resume": "python -m agent resume x"}, "run_id": rid}))
    return rd


def test_the_status_says_what_the_run_waits_for_and_lists_the_actions(tmp_path):
    rd = paused(tmp_path / "runs")
    p = NS._pending(rd)
    assert p["kind"] == "permission" and p["needs"] == ["run_vivado"] and p["actions"][0]["label"].startswith("Run Vivado") and p["mode"] == "ask"
    s = NS.summarise(tmp_path / "runs", rd.name)
    assert any("waiting for your permission at stage 3" in b and "run_vivado" in b for b in s["blocked"]) and "once you allow it" in s["next"]


def test_a_permission_question_is_answered_allow_or_deny_and_nothing_else(env):
    rc, _, sp = make_rc(env)
    paused(env["runs"])
    rid = "20261120-100000-abcd"
    for bad in ("yes please", "allow; rm -rf /", "", 5, None):
        r = rc.start({"kind": "answer", "run": rid, "answer": bad, "confirm": "start"})
        assert r["started"] is False and "allow or deny" in r["refused"]
    assert not sp.calls
    r = rc.start({"kind": "answer", "run": rid, "answer": "allow", "confirm": "start"})
    assert r["started"], r
    a = sp.calls[0]["argv"]
    assert a[2:5] == ["agent", "resume", rid] and json.loads(a[a.index("--reply") + 1]) == {"decision": "allow", "by": "you (Navigator)"}


def test_an_answer_to_a_run_that_is_not_asking_a_permission_still_needs_its_own_question(env):
    rc, _, sp = make_rc(env)
    paused(env["runs"], kind="review")
    r = rc.start({"kind": "answer", "run": "20261120-100000-abcd", "answer": "allow", "confirm": "start"})
    assert r["started"] is False and "not waiting" in r["refused"]


# --- the settings panel's API --------------------------------------------------------------------------------------------------------------

def test_the_panel_api_lists_the_actions_the_modes_the_never_list_and_the_settings(web):
    d = json.loads(web.get("/api/permissions")[2])
    assert {a["name"] for a in d["actions"]} == NAMES and [m["name"] for m in d["modes"]] == ["plan", "ask", "auto", "full"]
    assert all(set(a["modes"]) == {"plan", "ask", "auto", "full"} and a["plain"] for a in d["actions"])
    assert {n["id"] for n in d["never"]} == {r.id for r in P.NEVER} and d["hard_cap_usd"] == P.HARD_CAP_USD
    assert d["settings"]["mode"] == "ask" and d["settings"]["saved"] is False and "default" in d["settings"]["source"]
    assert d["effective"]["run_simulation"]["value"] == "allow" and d["effective"]["run_vivado"]["value"] == "ask"
    assert "c10_dds_sine" in d["projects"] and d["cli"].startswith("python -m agent run <spec> --permissions ask")


def test_saving_writes_the_file_the_command_line_reads_and_is_per_project(web):
    st, j = web.post("/api/permissions/save", {"project": "c10_dds_sine", "mode": "auto", "overrides": {"run_vivado": "deny", "run_simulation": "allow"}, "ask_above_usd": 2, "confirm": "save"})
    assert st == 200 and j["ok"] is True and j["settings"]["mode"] == "auto" and j["settings"]["saved"] is True and j["effective"]["run_vivado"]["value"] == "deny"
    f = web.env["cfg"] / "permissions.yaml"
    assert f.is_file() and web.app.perm_file == f
    saved = yaml.safe_load(f.read_text())
    assert saved["projects"]["c10_dds_sine"] == {"mode": "auto", "overrides": {"run_vivado": "deny"}, "ask_above_usd": 2.0}      # only the real difference is stored
    assert "--deny run_vivado" in j["cli"]
    spec = P.resolve(project="c10_dds_sine", config_file=f)                                                              # the command line resolves the same
    assert spec["mode"] == "auto" and spec["overrides"] == {"run_vivado": "deny"}
    other = json.loads(web.get("/api/permissions?project=")[2])
    assert other["settings"]["mode"] == "ask" and other["settings"]["saved"] is False                                    # another project is unchanged
    st, j2 = web.post("/api/permissions/save", {"project": None, "mode": "plan", "overrides": {}, "confirm": "save"})
    assert j2["ok"] and json.loads(web.get("/api/permissions?project=c10_dds_sine")[2])["settings"]["mode"] == "auto"      # the project entry still wins over the default


@pytest.mark.parametrize("body,why", [({"mode": "auto"}, "confirmation"), ({"mode": "auto", "confirm": "save", "argv": ["x"]}, "fields this action does not take"),
                                      ({"mode": "auto", "confirm": "save", "project": "../../etc"}, "pick a project"), ({"mode": "wild", "confirm": "save"}, "unknown permission mode"),
                                      ({"mode": "auto", "confirm": "save", "overrides": {"flash_it": "allow"}}, "bad override"), ({"mode": "auto", "confirm": "save", "overrides": {"run_vivado": "perhaps"}}, "bad override"),
                                      ({"mode": "auto", "confirm": "save", "ask_above_usd": -1}, "ask-above"), ({"mode": "auto", "confirm": "save", "ask_above_usd": True}, "ask-above")])
def test_a_bad_save_is_refused_and_writes_nothing(web, body, why):
    st, j = web.post("/api/permissions/save", body)
    assert st == 200 and j["ok"] is False and why in j["refused"]
    assert not (web.env["cfg"] / "permissions.yaml").exists()


def test_the_save_route_has_the_same_post_rules_as_every_action(web):
    ok = {"X-Navigator-Token": TOKEN, "Content-Type": "application/json", "Origin": f"http://127.0.0.1:{web.port}"}
    body = json.dumps({"mode": "auto", "confirm": "save"})
    assert web.req("POST", "/api/permissions/save", {k: v for k, v in ok.items() if k != "X-Navigator-Token"}, body)[0] == 401
    assert web.req("POST", "/api/permissions/save", {"Cookie": f"fda_nav={TOKEN}", "Content-Type": "application/json", "Origin": ok["Origin"]}, body)[0] == 403
    assert web.req("POST", "/api/permissions/save", {**ok, "Origin": "http://evil.example"}, body)[0] == 403
    assert web.req("POST", "/api/permissions/save", {**ok, "Content-Type": "text/plain"}, body)[0] == 403
    assert not (web.env["cfg"] / "permissions.yaml").exists()


def test_the_save_needs_the_access_gate(env):
    from navigator.tests.test_103_navigator import make_app

    def closed(entry):
        raise RuntimeError("revoked")
    app, _ = make_app(env["tmp"], gate=closed)
    code, _, body, _ = app.post("/api/permissions/save", {"mode": "auto", "confirm": "save"})
    assert code == 403 and json.loads(body)["ok"] is False


# --- the board gate ---------------------------------------------------------------------------------------------------------------------------

def test_read_only_board_actions_follow_the_default_settings(web):
    assert web.post("/api/board/run", {"board": "kr260", "action": "all", "confirm": "read"})[1]["ok"] is True      # Ask: the confirmation click is the ask
    assert json.loads(web.get("/api/board")[2])["permission"]["result"] == "ask"
    web.post("/api/permissions/save", {"project": None, "mode": "plan", "overrides": {}, "confirm": "save"})
    st, b = web.post("/api/board/run", {"board": "kr260", "action": "all", "confirm": "read"})
    assert b["ok"] is False and "off in the saved permission settings" in b["refused"] and len(web.tr.scripts) == 1       # Plan: refused, no script ran
    assert json.loads(web.get("/api/board")[2])["permission"]["result"] == "deny"
    web.post("/api/permissions/save", {"project": None, "mode": "plan", "overrides": {"read_board": "allow"}, "confirm": "save"})
    assert web.post("/api/board/run", {"board": "kr260", "action": "all", "confirm": "read"})[1]["ok"] is True


# --- the shipped page ---------------------------------------------------------------------------------------------------------------------------

def test_the_page_has_the_permissions_route_the_never_list_and_no_external_host():
    js = (ROOT / "navigator" / "static" / "app.js").read_text()
    assert 'permissions: pagePermissions' in js and '["permissions", "Permissions"]' in js and "Never allowed, in any mode" in js and "perm-question" in js
    assert set(re.findall(r"https?://[^\"' ]+", js)) <= {"http://www.w3.org/2000/svg"} and "innerHTML" not in js           # only the SVG namespace, which is a name and not a request
