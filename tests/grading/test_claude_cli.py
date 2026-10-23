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
            "messages": [{"role": "user", "content": [solution, {"type": "text", "text": "השאלות"},
                                                      {"type": "text", "text": "עמוד 1:"}, image]}]}


class FakeRun:
    """במקום subprocess.run: שומר את הפקודה ואת מה ששלחו ב-stdin, ועונה ב-stdout."""

    def __init__(self, stdout="", returncode=0, raises=None):
        self.stdout, self.returncode, self.raises = stdout, returncode, raises
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        if self.raises:
            raise self.raises
        return subprocess.CompletedProcess(cmd, self.returncode, stdout=self.stdout, stderr="")


def output(answer=ANSWER, **extra) -> str:
    """כמו הפלט של --output-format stream-json: שורת הודעה ובסוף שורת result"""
    return json.dumps({"type": "assistant"}) + chr(10) + json.dumps(
        {"type": "result", "is_error": False, "structured_output": answer, **extra})


def ask(run):
    return claude_cli.cli_ask("claude", grading.SCHEMA, "medium", run=run, error=grading.GradingError,
                              not_logged_in=grading.NoApiKey)


def test_one_message_with_everything_and_no_tools():
    run = FakeRun(output())
    assert json.loads(ask(run)(request())) == ANSWER
    (cmd, kwargs), = run.calls
    folder = Path(kwargs["cwd"])
    assert cmd[cmd.index("--tools") + 1] == "" and "--no-chrome" in cmd and "--strict-mcp-config" in cmd
    assert "--add-dir" not in cmd and cmd[cmd.index("--model") + 1] == "claude-opus-5-5"
    assert cmd[cmd.index("--input-format") + 1] == "stream-json" and cmd[cmd.index("--effort") + 1] == "medium"
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == grading.SCHEMA
    system = Path(cmd[cmd.index("--system-prompt-file") + 1])
    assert system.read_text(encoding="utf-8") == "אתה מתרגל" and system.parent == folder
    message = json.loads(kwargs["input"])["message"]  # הבקשה כולה ב-stdin, כולל התמונות
    kinds = [b["type"] for b in message["content"]]
    assert kinds == ["document", "text", "text", "image"]
    assert message["content"][3]["source"]["data"] == base64.b64encode(PNG).decode()


def test_work_folder_and_system_file_are_stable_so_the_cache_is_shared():
    assert claude_cli.work_folder() == claude_cli.work_folder()
    folder = claude_cli.work_folder()
    assert claude_cli.system_file(folder, "א") == claude_cli.system_file(folder, "א")
    assert claude_cli.system_file(folder, "א") != claude_cli.system_file(folder, "ב")


def test_shared_context_is_cached_for_an_hour():
    req = request()
    req["messages"][0]["content"][1]["cache_control"] = {"type": "ephemeral"}
    blocks = json.loads(claude_cli.message_line(req))["message"]["content"]
    assert blocks[1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"} and "cache_control" not in blocks[0]


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
    monkeypatch.setattr(claude_cli, "cli_ask", lambda claude, schema, effort, **k: seen.update(claude=claude) or (lambda req: req))
    ask = grading.claude_ask()
    assert callable(ask) and seen == {"claude": "claude"}
    monkeypatch.setattr(claude_driver, "auth_status", lambda *a, **k: {"logged_in": False, "message": ""})
    with pytest.raises(grading.NoApiKey) as e:
        grading.claude_ask()
    assert "claude auth login" in str(e.value) and "ANTHROPIC_API_KEY" in str(e.value)
