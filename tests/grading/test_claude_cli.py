"""בדיקה דרך Claude Code (grading/claude_cli.py), בלי להפעיל את claude באמת."""
from __future__ import annotations

import base64
import inspect
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from grading import claude_cli, grade as grading
from moodle import claude_code

ANSWER = {"questions": [{"label": "שאלה 1", "points": 10, "comment": "יפה"}], "feedback": "עבודה טובה",
          "annotations": [], "needs_review": False, "review_reason": ""}
PNG = b"\x89PNG\r\n\x1a\nfake page"


def request() -> dict:
    image = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(PNG).decode()}}
    solution = {"type": "document", "title": "Official solution.pdf",
                "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(b"%PDF sol").decode()}}
    return {"model": "claude-opus-5-5", "system": "אתה מתרגל", "max_tokens": 10,
            "messages": [{"role": "user", "content": [solution, {"type": "text", "text": "השאלות"},
                                                      {"type": "text", "text": "עמוד 1:"}, image]}]}


class FakeRun:
    """במקום subprocess.run: שומר את הפקודה ואת מה שהיה בתיקייה, ועונה ב-stdout."""

    def __init__(self, stdout="", returncode=0, raises=None):
        self.stdout, self.returncode, self.raises = stdout, returncode, raises
        self.calls, self.seen = [], []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        self.seen.append({p.name: p.read_bytes() for p in Path(kwargs["cwd"]).iterdir()})
        if self.raises:
            raise self.raises
        return subprocess.CompletedProcess(cmd, self.returncode, stdout=self.stdout, stderr="")


def output(answer=ANSWER, **extra) -> str:
    return json.dumps({"type": "result", "is_error": False, "structured_output": answer, **extra})


def ask(run):
    return claude_cli.cli_ask("claude", grading.SCHEMA, "high", run=run, error=grading.GradingError,
                              not_logged_in=grading.NoApiKey)


def test_pages_go_to_a_temp_folder_and_only_read_is_allowed():
    run = FakeRun(output())
    assert json.loads(ask(run)(request())) == ANSWER
    (cmd, kwargs), = run.calls
    folder = Path(kwargs["cwd"])
    assert cmd[cmd.index("--tools") + 1] == "Read" and "--no-chrome" in cmd and "--strict-mcp-config" in cmd
    assert cmd[cmd.index("--add-dir") + 1] == str(folder) and cmd[cmd.index("--model") + 1] == "claude-opus-5-5"
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == grading.SCHEMA
    assert cmd[cmd.index("--effort") + 1] == "high"
    files = run.seen[0]
    # העמודים נקראים לפי מספר העמוד והמסמכים בנפרד: כשהפתרון היה 001 ועמוד 1 היה 002, Claude דיווח לפעמים את
    # מספר הקובץ כמספר העמוד והסימונים נפלו עמוד אחד מאוחר מדי (2026-11-11)
    assert files["page-01.png"] == PNG and files["attachment-1.pdf"] == b"%PDF sol" and files["system.txt"] == "אתה מתרגל".encode()
    assert not [f for f in files if f[0].isdigit()]
    prompt = kwargs["input"]  # הבקשה ב-stdin, לא בשורת הפקודה
    assert f"תמונת עמוד 1: {folder / 'page-01.png'}" in prompt and "עמוד 1:" in prompt and claude_cli.READ_ALL in prompt
    assert "Official solution.pdf" in prompt and "page-03 = עמוד 3" in claude_cli.READ_ALL
    assert not folder.exists()  # התיקייה נמחקת בסוף


def test_the_zoom_pass_sends_crops_not_pages_and_is_logged_as_locate(monkeypatch, tmp_path):
    req = request()
    req["file_prefix"] = "crop"
    run = FakeRun(output())
    logged = []
    monkeypatch.setattr(claude_cli, "log_usage", lambda out, model, purpose="grade": logged.append(purpose))
    ask(run)(req)
    files = run.seen[0]
    assert "crop-01.png" in files and not [f for f in files if f.startswith("page-")]
    assert claude_cli.READ_CROPS in run.calls[0][1]["input"] and claude_cli.READ_ALL not in run.calls[0][1]["input"]
    assert logged == ["locate"]


def test_failures_become_grading_errors():
    with pytest.raises(grading.GradingError, match="דקות"):
        ask(FakeRun(raises=subprocess.TimeoutExpired("claude", 900)))(request())
    with pytest.raises(grading.GradingError):
        ask(FakeRun("not json"))(request())
    with pytest.raises(grading.NoApiKey):
        ask(FakeRun(json.dumps({"type": "result", "is_error": True, "result": "Not logged in · Please run /login"})))(request())


# ריצה שמשאירה אחריה תהליך שמחזיק את הפלט שלה פתוח, וכותב לקובץ כל עשירית שנייה כל עוד הוא חי
LEAVES_A_CHILD = r'''
import subprocess, sys, time
sys.stdin.read()
subprocess.Popen([sys.executable, "-c",
    "import sys, time\nwhile True:\n    open(sys.argv[1], 'a').write('.')\n    time.sleep(0.1)", sys.argv[1]])
time.sleep(60)
'''


def within(seconds: float, call) -> dict:
    """Runs `call` in a thread and waits for it at most `seconds`: a test of a hang must not hang the tests."""
    done: dict = {}

    def go():
        t = time.monotonic()
        try:
            call()
            done["result"] = "returned"
        except subprocess.TimeoutExpired:
            done["result"] = "TimeoutExpired"
        done["seconds"] = time.monotonic() - t

    th = threading.Thread(target=go, daemon=True)
    th.start()
    th.join(seconds)
    return done


def test_a_run_past_its_time_is_stopped_with_everything_it_started(tmp_path):
    """2026-11-18: grading calls hung for an hour although the limit is 15 minutes. subprocess.run kills only the run
    itself, and on Windows then waits with no limit until its output closes; a process it started holds it open."""
    beat = tmp_path / "alive.txt"
    done = within(30, lambda: claude_cli.run_bounded([sys.executable, "-c", LEAVES_A_CHILD, str(beat)], input="x",
                                                     capture_output=True, text=True, encoding="utf-8", timeout=2))
    assert done.get("result") == "TimeoutExpired" and done["seconds"] < 15
    time.sleep(0.5)
    size = beat.stat().st_size
    time.sleep(1)
    assert beat.stat().st_size == size  # what the run started is dead too


def test_a_run_that_will_not_die_is_given_up_after_the_limit(monkeypatch):
    """If killing does not end it, the grading moves on to the next work instead of waiting for it forever."""
    monkeypatch.setattr(claude_cli, "_kill_tree", lambda proc: None)
    monkeypatch.setattr(claude_cli, "KILL_WAIT_S", 1)
    done = within(20, lambda: claude_cli.run_bounded([sys.executable, "-c", "import sys, time; sys.stdin.read(); "
                                                      "time.sleep(8)"], input="x", capture_output=True, text=True,
                                                     encoding="utf-8", timeout=1))
    assert done.get("result") == "TimeoutExpired" and done["seconds"] < 6


def test_a_run_in_time_returns_its_output():
    out = claude_cli.run_bounded([sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"], input="שלום ok",
                                 capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert out.returncode == 0 and out.stdout.strip() == "שלום OK"


def test_grading_runs_claude_with_the_limit_that_holds():
    assert inspect.signature(claude_cli.cli_ask).parameters["run"].default is claude_cli.run_bounded


def test_without_a_key_claude_ask_uses_claude_code(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(claude_code, "find_claude", lambda: "claude")
    monkeypatch.setattr(claude_code, "auth_status", lambda *a, **k: {"logged_in": True, "message": ""})
    seen = {}
    monkeypatch.setattr(claude_cli, "cli_ask", lambda claude, schema, effort, **k: seen.update(claude=claude) or "ask")
    assert grading.claude_ask() == "ask" and seen == {"claude": "claude"}
    monkeypatch.setattr(claude_code, "auth_status", lambda *a, **k: {"logged_in": False, "message": ""})
    with pytest.raises(grading.NoApiKey) as e:
        grading.claude_ask()
    assert "claude auth login" in str(e.value) and "ANTHROPIC_API_KEY" in str(e.value)
