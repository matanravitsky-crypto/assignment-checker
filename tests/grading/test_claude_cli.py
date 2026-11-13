"""בדיקה דרך Claude Code (grading/claude_cli.py), בלי להפעיל את claude באמת."""
from __future__ import annotations

import base64
import json
import subprocess
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
