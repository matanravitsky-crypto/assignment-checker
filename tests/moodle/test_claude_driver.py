import json
import subprocess
from pathlib import Path

import pytest

from moodle import claude_driver
from moodle.claude_driver import (
    GRADING_URL,
    NOT_INSTALLED,
    NOT_LOGGED_IN,
    RESULT_SCHEMA,
    UPLOAD_URL,
    DRY_RUN_MODE,
    ClaudeChromeDriver,
    auth_status,
    build_command,
    parse_result,
    render_prompt,
)
from moodle.send import UploadResult

INFO = {"id": "3438636", "title": "הגשה 0 - קבוצות ומרוכבים"}
ANSWER = {"status": "imported", "rows": 6, "imported": 6, "skipped": 0, "message": "6 imported"}


def cli_output(answer=ANSWER, **extra) -> str:
    """What `claude -p --output-format json` prints when the structured answer is in `structured_output`."""
    return json.dumps({"type": "result", "is_error": False, "structured_output": answer, **extra})


class FakeRun:
    """Stands in for subprocess.run: records the call, answers with `stdout`. Never starts a process."""

    def __init__(self, stdout="", returncode=0, raises=None):
        self.stdout, self.returncode, self.raises = stdout, returncode, raises
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        if self.raises:
            raise self.raises
        return subprocess.CompletedProcess(cmd, self.returncode, stdout=self.stdout, stderr="")


def driver(run, **kwargs) -> ClaudeChromeDriver:
    return ClaudeChromeDriver(run=run, claude="claude", **kwargs)


# ---------- the command and the prompt ----------
def test_command_is_limited_to_chrome_and_the_upload_folder(tmp_path):
    cmd = build_command("p", tmp_path, model="m", budget_usd=2.0, schema=RESULT_SCHEMA, claude="claude")
    assert {"-p", "--chrome", "--no-session-persistence"} <= set(cmd)
    assert cmd[cmd.index("--add-dir") + 1] == str(tmp_path)
    assert cmd[cmd.index("--allowedTools") + 1] == "mcp__claude-in-chrome"
    assert cmd[cmd.index("--tools") + 1] == ""  # built-in tools off: only the Chrome tools remain
    assert "Bash" not in " ".join(cmd)


def test_command_has_the_baseline_flags_and_the_prompt_last(tmp_path):
    cmd = build_command("the prompt", tmp_path, model="m", budget_usd=2.0, schema=RESULT_SCHEMA, claude="C:/bin/claude.exe")
    assert cmd[0] == "C:/bin/claude.exe"
    assert cmd[-1] == "the prompt"
    assert cmd[cmd.index("--setting-sources") + 1] == "project"
    assert "--strict-mcp-config" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert cmd[cmd.index("--max-budget-usd") + 1] == "2.0"
    assert cmd[cmd.index("--model") + 1] == "m"
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == RESULT_SCHEMA


@pytest.mark.parametrize("flag", ["--add-dir", "--allowedTools", "--tools"])
def test_a_flag_that_takes_a_list_never_swallows_the_prompt(tmp_path, flag):
    cmd = build_command("the prompt", tmp_path, model="m", budget_usd=2.0, schema=RESULT_SCHEMA, claude="claude")
    assert cmd[cmd.index(flag) + 2].startswith("--")


def test_prompt_has_the_assignment_zip_and_count(tmp_path):
    p = render_prompt(INFO, tmp_path / "Graded - part 01.zip", 6, dry_run=True)
    assert "id=3438636" in p and "Graded - part 01.zip" in p and "rows = 6" in p and "This is a dry run" in p


def test_prompt_names_one_address_and_the_assignment_title(tmp_path):
    p = render_prompt(INFO, tmp_path / "z.zip", 2, dry_run=False)
    assert UPLOAD_URL.format(id="3438636") in p
    assert "id=3438636" in p and '"הגשה 0 - קבוצות ומרוכבים"' in p
    assert "העלאת קובץ זה" in p and "יבוא קבצי משוב" in p
    assert DRY_RUN_MODE.split(":")[0] not in p  # "This is a dry run" is the dry-run text only
    assert "{" not in p and "}" not in p  # every placeholder was filled


def test_dry_run_never_imports_and_says_so_twice(tmp_path):
    p = render_prompt(INFO, tmp_path / "z.zip", 6, dry_run=True)
    assert "Never click יבוא קבצי משוב" in p and "ביטול" in p
    assert "In a dry run never click יבוא קבצי משוב" in p  # also in the rules, so it holds in any mode
    assert 'return "dry_run_ok" with rows = 6'.lower() in p.lower()


def test_real_run_clicks_import_once_and_reads_moodles_message(tmp_path):
    p = render_prompt(INFO, tmp_path / "z.zip", 6, dry_run=False)
    assert "This is a dry run" not in p and "Never click יבוא קבצי משוב." not in p
    assert "exactly once" in p and "never retry" in p
    assert "rows = imported + skipped" in p and "cannot be cancelled" in p
    assert "לא נמצאה הודעת תוצאה ממודל" in p


def test_template_knows_there_is_no_confirmation_screen():
    text = claude_driver.TEMPLATE.read_text(encoding="utf-8").lower()
    for gone in ("confirmation list", "count the rows", "javascript_tool", "get_page_text", "click cancel"):
        assert gone not in text


def test_defaults_keep_sonnet_and_enough_budget():
    assert claude_driver.DEFAULT_MODEL == "claude-sonnet-5-5"
    assert claude_driver.DEFAULT_BUDGET_USD >= 1.0  # real Sonnet runs cost 0.10-0.34 USD


def test_urls_follow_the_global_constraints():
    assert UPLOAD_URL == ("https://moodle.bgu.ac.il/moodle/mod/assign/view.php?id={id}&plugin=file"
                          "&pluginsubtype=assignfeedback&action=viewpluginpage&pluginaction=uploadzip")
    assert GRADING_URL == "https://moodle.bgu.ac.il/moodle/mod/assign/view.php?id={id}&action=grading"


def test_result_schema_asks_for_every_field():
    assert set(RESULT_SCHEMA["required"]) == {"status", "rows", "imported", "skipped", "message"}
    assert set(RESULT_SCHEMA["properties"]["status"]["enum"]) == {
        "imported", "dry_run_ok", "needs_login", "mismatch", "error"}
    assert RESULT_SCHEMA["properties"]["message"]["maxLength"] == 300


# ---------- reading the answer ----------
def test_parse_result_reads_the_structured_answer():
    out = json.dumps({"is_error": False, "structured_output": {"status": "imported", "rows": 6, "imported": 6, "skipped": 0, "message": "6 imported"}})
    assert parse_result(out) == UploadResult("imported", 6, 6, 0, "6 imported")


@pytest.mark.parametrize("result", [
    json.dumps(ANSWER),
    "```json\n" + json.dumps(ANSWER) + "\n```",
])
def test_parse_result_falls_back_to_json_inside_result(result):
    out = json.dumps({"is_error": False, "result": result})
    assert parse_result(out) == UploadResult("imported", 6, 6, 0, "6 imported")


def test_parse_result_takes_the_result_entry_of_a_list():
    out = json.dumps([{"type": "system"}, json.loads(cli_output())])
    assert parse_result(out).status == "imported"


def test_parse_result_keeps_null_counts_and_caps_the_message():
    out = cli_output({"status": "needs_login", "rows": None, "imported": None, "skipped": None, "message": "x" * 500})
    r = parse_result(out)
    assert (r.status, r.rows, r.imported, r.skipped) == ("needs_login", None, None, None)
    assert r.message == "x" * 300


@pytest.mark.parametrize("status", ["needs_login", "mismatch", "error"])
def test_a_failing_status_without_a_message_gets_a_hebrew_one(status):
    r = parse_result(cli_output({"status": status, "rows": None, "imported": None, "skipped": None, "message": ""}))
    assert r.status == status and r.message


@pytest.mark.parametrize("stdout, expect", [
    (json.dumps({"is_error": True, "result": "Failed to authenticate: OAuth session expired"}), NOT_LOGGED_IN),
    (json.dumps({"is_error": True, "result": "Invalid API key · Please run /login"}), NOT_LOGGED_IN),
    ("not json", "תשובה לא צפויה"),
    ("", "תשובה לא צפויה"),
    (json.dumps({"is_error": False, "result": "I could not do it."}), "תשובה לא צפויה"),
    (json.dumps({"is_error": False, "structured_output": {"status": "maybe"}}), "תשובה לא צפויה"),
    (json.dumps(["x"]), "תשובה לא צפויה"),
    (json.dumps({"is_error": True, "result": "Credit balance is too low"}), "Credit balance is too low"),
    (json.dumps({"is_error": False, "subtype": "error_max_budget_usd"}), "error_max_budget_usd"),
])
def test_parse_result_errors(stdout, expect):
    r = parse_result(stdout)
    assert r.status == "error" and expect in r.message


# ---------- the driver ----------
def test_timeout_is_an_error(tmp_path):
    def run(*a, **k):
        raise subprocess.TimeoutExpired("claude", 1)
    r = ClaudeChromeDriver(run=run, claude="claude").upload_zip(INFO, tmp_path / "z.zip", 1, False)
    assert r.status == "error"


def test_upload_zip_runs_one_locked_down_command_in_the_upload_folder(tmp_path):
    fake = FakeRun(cli_output())
    r = driver(fake, model="the-model", budget_usd=1.5, timeout_s=77).upload_zip(INFO, tmp_path / "Graded - part 01.zip", 6, False)
    assert r == UploadResult("imported", 6, 6, 0, "6 imported")
    (cmd, kwargs), = fake.calls
    assert cmd[0] == "claude" and cmd[cmd.index("--add-dir") + 1] == str(tmp_path)
    assert cmd[cmd.index("--model") + 1] == "the-model" and cmd[cmd.index("--max-budget-usd") + 1] == "1.5"
    assert "expected 6" in cmd[-1] and "Graded - part 01.zip" in cmd[-1] and "This is a dry run" not in cmd[-1]
    assert kwargs["capture_output"] is True and kwargs["text"] is True and kwargs["encoding"] == "utf-8"
    assert kwargs["timeout"] == 77 and Path(kwargs["cwd"]) == tmp_path


def test_upload_zip_dry_run_is_in_the_prompt(tmp_path):
    fake = FakeRun(cli_output({**ANSWER, "status": "dry_run_ok", "imported": None, "skipped": None}))
    r = driver(fake).upload_zip(INFO, tmp_path / "z.zip", 6, True)
    assert r.status == "dry_run_ok" and "This is a dry run" in fake.calls[0][0][-1]


def test_upload_zip_without_claude_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_driver, "find_claude", lambda: None)
    fake = FakeRun(cli_output())
    r = ClaudeChromeDriver(run=fake).upload_zip(INFO, tmp_path / "z.zip", 1, False)
    assert r == UploadResult("error", message=NOT_INSTALLED) and fake.calls == []


def test_upload_zip_finds_claude_on_the_path(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_driver.shutil, "which", lambda name: "C:/Users/x/.local/bin/claude.exe")
    fake = FakeRun(cli_output())
    ClaudeChromeDriver(run=fake).upload_zip(INFO, tmp_path / "z.zip", 1, False)
    assert fake.calls[0][0][0] == "C:/Users/x/.local/bin/claude.exe"


def test_a_missing_executable_is_not_installed(tmp_path):
    r = driver(FakeRun(raises=FileNotFoundError("claude"))).upload_zip(INFO, tmp_path / "z.zip", 1, False)
    assert r == UploadResult("error", message=NOT_INSTALLED)


def test_timeout_message_says_how_long_and_that_retry_is_safe(tmp_path):
    r = driver(FakeRun(raises=subprocess.TimeoutExpired("claude", 600)), timeout_s=600).upload_zip(INFO, tmp_path / "z.zip", 1, False)
    assert r.status == "error" and "10" in r.message


def test_a_failed_exit_without_output_is_an_error_with_the_exit_code(tmp_path):
    r = driver(FakeRun("", returncode=3)).upload_zip(INFO, tmp_path / "z.zip", 1, False)
    assert r.status == "error" and "3" in r.message


def test_a_failed_exit_with_an_auth_error_says_not_logged_in(tmp_path):
    out = json.dumps({"is_error": True, "result": "Failed to authenticate: OAuth session expired"})
    r = driver(FakeRun(out, returncode=1)).upload_zip(INFO, tmp_path / "z.zip", 1, False)
    assert r == UploadResult("error", message=NOT_LOGGED_IN)


def test_a_failed_exit_never_counts_as_an_upload(tmp_path):
    r = driver(FakeRun(cli_output(), returncode=1)).upload_zip(INFO, tmp_path / "z.zip", 6, False)
    assert r.status == "error"


def test_needs_login_from_claude_passes_through(tmp_path):
    out = cli_output({"status": "needs_login", "rows": None, "imported": None, "skipped": None, "message": "login page"})
    assert driver(FakeRun(out)).upload_zip(INFO, tmp_path / "z.zip", 1, False) == UploadResult("needs_login", message="login page")


@pytest.mark.parametrize("error", [OSError("boom"), PermissionError("no"), RuntimeError("odd"), UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")])
def test_the_driver_never_raises(tmp_path, error):
    r = driver(FakeRun(raises=error)).upload_zip(INFO, tmp_path / "z.zip", 1, False)
    assert r.status == "error" and r.message


@pytest.mark.parametrize("info", [{"title": "no id"}, {"id": "12 34", "title": "t"}, {"id": "1&action=x", "title": "t"}])
def test_a_bad_info_dict_is_an_error_and_nothing_runs(tmp_path, info):
    fake = FakeRun(cli_output())
    r = driver(fake).upload_zip(info, tmp_path / "z.zip", 1, False)
    assert r.status == "error" and fake.calls == []


# ---------- check and auth_status ----------
CHECK_OK = {"chrome": True, "moodle_logged_in": True}


def test_check_reports_chrome_and_moodle(tmp_path):
    fake = FakeRun(cli_output(CHECK_OK))
    out = driver(fake).check(INFO)
    assert out["chrome"] is True and out["moodle"] is True and out["message"] and out["answered"] is True
    cmd = fake.calls[0][0]
    assert GRADING_URL.format(id="3438636") in cmd[-1]
    assert cmd[cmd.index("--allowedTools") + 1] == "mcp__claude-in-chrome"
    assert "--chrome" in cmd and "--no-session-persistence" in cmd
    # No ZIP to carry here, so the only folder it may see is an empty one made for the check
    assert cmd[cmd.index("--add-dir") + 1] == str(fake.calls[0][1]["cwd"])


def test_check_says_what_is_missing():
    out = driver(FakeRun(cli_output({"chrome": True, "moodle_logged_in": False}))).check(INFO)
    assert out["chrome"] is True and out["moodle"] is False and "Moodle" in out["message"]
    out = driver(FakeRun(cli_output({"chrome": False, "moodle_logged_in": False}))).check(INFO)
    assert out["chrome"] is False and out["moodle"] is False and "Chrome" in out["message"]
    assert out["answered"] is True  # Claude really looked: "no" is an answer


@pytest.mark.parametrize("run", [
    FakeRun(raises=subprocess.TimeoutExpired("claude", 1)),
    FakeRun(raises=FileNotFoundError("claude")),
    FakeRun(raises=RuntimeError("odd")),
    FakeRun("not json"),
    FakeRun("", returncode=1),
])
def test_check_never_raises(run):
    out = driver(run).check(INFO)
    assert out["chrome"] is False and out["moodle"] is False and out["message"]
    assert "answered" not in out  # a failure to run is not an answer: the site does not remember it


def test_check_without_claude_installed(monkeypatch):
    monkeypatch.setattr(claude_driver, "find_claude", lambda: None)
    assert ClaudeChromeDriver(run=FakeRun()).check(INFO) == {"chrome": False, "moodle": False, "message": NOT_INSTALLED}


def test_check_not_logged_in_to_claude():
    out = json.dumps({"is_error": True, "result": "Invalid API key · Please run /login"})
    assert driver(FakeRun(out, returncode=1)).check(INFO) == {"chrome": False, "moodle": False, "message": NOT_LOGGED_IN}


def test_auth_status_logged_out_and_in():
    fake = FakeRun(json.dumps({"loggedIn": False, "authMethod": "none"}), returncode=1)
    assert auth_status(run=fake, claude="claude") == {"logged_in": False, "message": NOT_LOGGED_IN}
    assert fake.calls[0][0] == ["claude", "auth", "status", "--json"]
    out = auth_status(run=FakeRun(json.dumps({"loggedIn": True, "authMethod": "claude.ai"})), claude="claude")
    assert out["logged_in"] is True and out["message"]


def test_auth_status_never_raises(monkeypatch):
    for run in (FakeRun(raises=FileNotFoundError("claude")), FakeRun(raises=subprocess.TimeoutExpired("claude", 1)),
                FakeRun("not json"), FakeRun("")):
        out = auth_status(run=run, claude="claude")
        assert out["logged_in"] is False and out["message"]
    monkeypatch.setattr(claude_driver, "find_claude", lambda: None)
    assert auth_status(run=FakeRun()) == {"logged_in": False, "message": NOT_INSTALLED}


def test_find_claude_falls_back_to_the_installers_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_driver.shutil, "which", lambda name: None)
    monkeypatch.setattr(claude_driver.Path, "home", lambda: tmp_path)
    assert claude_driver.find_claude() is None
    bin_dir = tmp_path / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "claude").write_text("x")
    assert claude_driver.find_claude() == str(bin_dir / "claude")
    (bin_dir / "claude.exe").write_text("x")
    assert claude_driver.find_claude() == str(bin_dir / "claude.exe")  # the Windows name comes first
    monkeypatch.setattr(claude_driver.shutil, "which", lambda name: "C:/on/path/claude.exe")
    assert claude_driver.find_claude() == "C:/on/path/claude.exe"  # the PATH wins


def test_the_driver_and_auth_status_use_the_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_driver, "find_claude", lambda: "C:/home/.local/bin/claude.exe")
    fake = FakeRun(cli_output())
    ClaudeChromeDriver(run=fake).upload_zip(INFO, tmp_path / "z.zip", 1, False)
    assert fake.calls[0][0][0] == "C:/home/.local/bin/claude.exe"
    status = FakeRun(json.dumps({"loggedIn": True}))
    assert auth_status(run=status)["logged_in"] is True and status.calls[0][0][0] == "C:/home/.local/bin/claude.exe"
