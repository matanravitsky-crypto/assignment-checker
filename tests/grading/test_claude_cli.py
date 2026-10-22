"""בדיקה דרך Claude Code (grading/claude_cli.py), בלי להפעיל את claude באמת."""
from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

import pytest

from grading import claude_cli, grade as grading
from moodle import claude_driver

ANSWER = {"questions": [{"label": "שאלה 1", "points": 10, "comment": "יפה"}], "feedback": "עבודה טובה",
          "annotations": [], "needs_review": False, "review_reason": ""}
PNG = b"\x89PNG\r\n\x1a\nfake page"


def request() -> dict:
    image = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(PNG).decode()}}
    solution = {"type": "document", "title": "Official solution.pdf",
                "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(b"%PDF sol").decode()}}
    return {"model": "claude-opus-5-5", "system": "אתה מתרגל", "max_tokens": 10,
            "messages": [{"role": "user", "content": [solution, {"type": "text", "text": "השאלות", "cache_control": {"type": "ephemeral"}},
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


def test_pages_go_inside_the_message_and_no_tool_is_allowed():
    run = FakeRun(output())
    assert json.loads(ask(run)(request())) == ANSWER
    (cmd, kwargs), = run.calls
    folder = Path(kwargs["cwd"])
    assert cmd[cmd.index("--tools") + 1] == "" and "--no-chrome" in cmd and "--strict-mcp-config" in cmd
    assert "--add-dir" not in cmd and cmd[cmd.index("--model") + 1] == "claude-opus-5-5"
    assert cmd[cmd.index("--input-format") + 1] == "stream-json"
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == grading.SCHEMA
    assert cmd[cmd.index("--effort") + 1] == "high"
    # בתיקייה רק ה-system prompt, עם מה שמשותף לכל ההגשות (מה שמסומן ב-cache_control)
    assert run.seen[0] == {"system.txt": "אתה מתרגל\n\nהשאלות".encode()}
    # ההודעה ב-stdin: הפתרון והעמוד עצמם, בלי cache_control
    message = json.loads(kwargs["input"])
    content = message["message"]["content"]
    assert message["type"] == "user" and [b["type"] for b in content] == ["document", "text", "image"]
    assert base64.b64decode(content[2]["source"]["data"]) == PNG and "cache_control" not in kwargs["input"]
    assert not folder.exists()  # התיקייה נמחקת בסוף


def test_one_by_one_asks_to_go_over_each_page():
    run = FakeRun(output())
    ask(run)({**request(), "_one_by_one": True})
    content = json.loads(run.calls[0][1]["input"])["message"]["content"]
    assert content[-1] == {"type": "text", "text": claude_cli.READ_ONE_BY_ONE}


def test_stream_json_output_is_read():
    lines = [json.dumps({"type": "system"}), json.dumps({"type": "assistant"}), output()]
    assert json.loads(ask(FakeRun("\n".join(lines)))(request())) == ANSWER


def test_failures_become_grading_errors():
    with pytest.raises(grading.GradingError, match="דקות"):
        ask(FakeRun(raises=subprocess.TimeoutExpired("claude", 900)))(request())
    with pytest.raises(grading.GradingError):
        ask(FakeRun("not json"))(request())
    with pytest.raises(grading.NoApiKey):
        ask(FakeRun(json.dumps({"type": "result", "is_error": True, "result": "Not logged in · Please run /login"})))(request())


def test_without_a_key_claude_ask_uses_claude_code(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(claude_driver, "find_claude", lambda: "claude")
    monkeypatch.setattr(claude_driver, "auth_status", lambda *a, **k: {"logged_in": True, "message": ""})
    seen = {}
    monkeypatch.setattr(claude_cli, "cli_ask", lambda claude, schema, effort, **k: seen.update(claude=claude) or "ask")
    assert grading.claude_ask() == "ask" and seen == {"claude": "claude"}
    monkeypatch.setattr(claude_driver, "auth_status", lambda *a, **k: {"logged_in": False, "message": ""})
    with pytest.raises(grading.NoApiKey) as e:
        grading.claude_ask()
    assert "claude auth login" in str(e.value) and "ANTHROPIC_API_KEY" in str(e.value)
