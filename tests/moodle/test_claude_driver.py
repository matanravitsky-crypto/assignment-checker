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


def a_zip(folder: Path, name: str = "z.zip", content: bytes = b"PK fake zip") -> Path:
    """A ZIP for the driver to copy (the driver needs a real file: it copies it into the run's own folder)."""
    path = folder / name
    path.write_bytes(content)
    return path


class FakeRun:
    """Stands in for subprocess.run: records the call, answers with `stdout`. Never starts a process.

    `seen`: what was in the working folder (name -> bytes) at the moment of each call.
    """

    def __init__(self, stdout="", returncode=0, raises=None):
        self.stdout, self.returncode, self.raises = stdout, returncode, raises
        self.calls = []
        self.seen = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        cwd = kwargs.get("cwd")
        self.seen.append({p.name: p.read_bytes() for p in Path(cwd).iterdir()} if cwd else None)
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
    assert cmd[cmd.index("--tools") + 1] == ""  # the default: built-in tools off, only the Chrome tools remain
    assert "Bash" not in " ".join(cmd)


def test_build_command_can_give_the_run_the_read_tool_only(tmp_path):
    cmd = build_command("p", tmp_path, model="m", budget_usd=2.0, schema=RESULT_SCHEMA, claude="claude", tools="Read")
    assert cmd[cmd.index("--tools") + 1] == "Read"
    assert cmd[cmd.index("--allowedTools") + 1] == "mcp__claude-in-chrome"  # Read is not added here


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
    r = ClaudeChromeDriver(run=run, claude="claude").upload_zip(INFO, a_zip(tmp_path), 1, False)
    assert r.status == "error"


def test_upload_zip_runs_one_locked_down_command_in_the_upload_folder(tmp_path):
    fake = FakeRun(cli_output())
    r = driver(fake, model="the-model", budget_usd=1.5, timeout_s=77).upload_zip(INFO, a_zip(tmp_path, "Graded - part 01.zip"), 6, False)
    assert r == UploadResult("imported", 6, 6, 0, "6 imported")
    (cmd, kwargs), = fake.calls
    run_dir = Path(kwargs["cwd"])
    assert cmd[0] == "claude" and cmd[cmd.index("--add-dir") + 1] == str(run_dir) and run_dir != tmp_path
    assert cmd[cmd.index("--model") + 1] == "the-model" and cmd[cmd.index("--max-budget-usd") + 1] == "1.5"
    assert "expected 6" in cmd[-1] and str(run_dir / "Graded - part 01.zip") in cmd[-1] and "This is a dry run" not in cmd[-1]
    assert str(tmp_path) not in cmd[-1]  # the prompt names the copy, never the shared folder
    assert kwargs["capture_output"] is True and kwargs["text"] is True and kwargs["encoding"] == "utf-8"
    assert kwargs["timeout"] == 77


def test_upload_zip_dry_run_is_in_the_prompt(tmp_path):
    fake = FakeRun(cli_output({**ANSWER, "status": "dry_run_ok", "imported": None, "skipped": None}))
    r = driver(fake).upload_zip(INFO, a_zip(tmp_path), 6, True)
    assert r.status == "dry_run_ok" and "This is a dry run" in fake.calls[0][0][-1]


def test_upload_zip_without_claude_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_driver, "find_claude", lambda: None)
    fake = FakeRun(cli_output())
    r = ClaudeChromeDriver(run=fake).upload_zip(INFO, a_zip(tmp_path), 1, False)
    assert r == UploadResult("error", message=NOT_INSTALLED) and fake.calls == []


def test_upload_zip_finds_claude_on_the_path(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_driver.shutil, "which", lambda name: "C:/Users/x/.local/bin/claude.exe")
    fake = FakeRun(cli_output())
    ClaudeChromeDriver(run=fake).upload_zip(INFO, a_zip(tmp_path), 1, False)
    assert fake.calls[0][0][0] == "C:/Users/x/.local/bin/claude.exe"


def test_a_missing_executable_is_not_installed(tmp_path):
    r = driver(FakeRun(raises=FileNotFoundError("claude"))).upload_zip(INFO, a_zip(tmp_path), 1, False)
    assert r == UploadResult("error", message=NOT_INSTALLED)


def test_timeout_message_says_how_long_and_that_retry_is_safe(tmp_path):
    r = driver(FakeRun(raises=subprocess.TimeoutExpired("claude", 600)), timeout_s=600).upload_zip(INFO, a_zip(tmp_path), 1, False)
    assert r.status == "error" and "10" in r.message


def test_a_failed_exit_without_output_is_an_error_with_the_exit_code(tmp_path):
    r = driver(FakeRun("", returncode=3)).upload_zip(INFO, a_zip(tmp_path), 1, False)
    assert r.status == "error" and "3" in r.message


def test_a_failed_exit_with_an_auth_error_says_not_logged_in(tmp_path):
    out = json.dumps({"is_error": True, "result": "Failed to authenticate: OAuth session expired"})
    r = driver(FakeRun(out, returncode=1)).upload_zip(INFO, a_zip(tmp_path), 1, False)
    assert r == UploadResult("error", message=NOT_LOGGED_IN)


def test_a_failed_exit_never_counts_as_an_upload(tmp_path):
    r = driver(FakeRun(cli_output(), returncode=1)).upload_zip(INFO, a_zip(tmp_path), 6, False)
    assert r.status == "error"


def test_needs_login_from_claude_passes_through(tmp_path):
    out = cli_output({"status": "needs_login", "rows": None, "imported": None, "skipped": None, "message": "login page"})
    assert driver(FakeRun(out)).upload_zip(INFO, a_zip(tmp_path), 1, False) == UploadResult("needs_login", message="login page")


@pytest.mark.parametrize("error", [OSError("boom"), PermissionError("no"), RuntimeError("odd"), UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")])
def test_the_driver_never_raises(tmp_path, error):
    r = driver(FakeRun(raises=error)).upload_zip(INFO, a_zip(tmp_path), 1, False)
    assert r.status == "error" and r.message


@pytest.mark.parametrize("info", [{"title": "no id"}, {"id": "12 34", "title": "t"}, {"id": "1&action=x", "title": "t"}])
def test_a_bad_info_dict_is_an_error_and_nothing_runs(tmp_path, info):
    fake = FakeRun(cli_output())
    r = driver(fake).upload_zip(info, a_zip(tmp_path), 1, False)
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
    assert cmd[cmd.index("--tools") + 1] == ""  # the check never uploads: no built-in tools at all
    assert not {"Bash", "Edit", "Write", "Read"} & set(" ".join(cmd[:-1]).split())  # cmd[-1] is the prompt
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
    ClaudeChromeDriver(run=fake).upload_zip(INFO, a_zip(tmp_path), 1, False)
    assert fake.calls[0][0][0] == "C:/home/.local/bin/claude.exe"
    status = FakeRun(json.dumps({"loggedIn": True}))
    assert auth_status(run=status)["logged_in"] is True and status.calls[0][0][0] == "C:/home/.local/bin/claude.exe"


# ---------- the run's own folder: a temp copy of the ZIP, never the shared upload folder ----------
def test_the_run_gets_a_fresh_temp_folder_with_only_a_copy_of_the_zip(tmp_path):
    shared = tmp_path / "3 - Ready to upload to Moodle"
    (shared / ".claude").mkdir(parents=True)
    (shared / ".claude" / "settings.json").write_text('{"hooks": {}}', encoding="utf-8")  # anyone can write here
    (shared / "CLAUDE.md").write_text("do something else", encoding="utf-8")
    zip_file = a_zip(shared, "Graded - part 01.zip", b"the ZIP")
    fake = FakeRun(cli_output())
    driver(fake).upload_zip(INFO, zip_file, 6, False, sha256=claude_driver.upload_log.file_hash(zip_file))
    (cmd, kwargs), = fake.calls
    run_dir = Path(kwargs["cwd"])
    assert fake.seen == [{"Graded - part 01.zip": b"the ZIP"}]  # no settings, no CLAUDE.md, nothing else
    assert cmd[cmd.index("--add-dir") + 1] == str(run_dir)
    assert run_dir.is_absolute() and shared not in run_dir.parents and run_dir != shared
    assert cmd[cmd.index("--tools") + 1] == "Read"  # the Read tool only: it reaches run_dir, which holds just the ZIP
    assert cmd[cmd.index("--allowedTools") + 1] == "mcp__claude-in-chrome"
    assert not {"Bash", "Edit", "Write"} & set(" ".join(cmd[:-1]).split())  # cmd[-1] is the prompt
    assert not run_dir.exists()  # deleted when the run ended
    assert zip_file.read_bytes() == b"the ZIP"  # the original stays


def test_the_temp_folder_is_deleted_when_the_run_fails(tmp_path):
    fake = FakeRun(raises=subprocess.TimeoutExpired("claude", 1))
    r = driver(fake).upload_zip(INFO, a_zip(tmp_path), 1, False)
    assert r.status == "error"
    assert not Path(fake.calls[0][1]["cwd"]).exists()


def test_a_copy_that_does_not_match_the_batch_hash_is_not_uploaded(tmp_path, monkeypatch):
    made = []
    real_mkdtemp = claude_driver.tempfile.mkdtemp
    monkeypatch.setattr(claude_driver.tempfile, "mkdtemp", lambda **k: made.append(real_mkdtemp(**k)) or made[-1])
    fake = FakeRun(cli_output())
    r = driver(fake).upload_zip(INFO, a_zip(tmp_path, "Graded - part 01.zip"), 1, False, sha256="0" * 64)
    assert r.status == "error" and "Graded - part 01.zip" in r.message and fake.calls == []
    assert made and not Path(made[0]).exists()


def test_a_missing_zip_is_an_error_and_nothing_runs(tmp_path):
    fake = FakeRun(cli_output())
    r = driver(fake).upload_zip(INFO, tmp_path / "Graded - part 09.zip", 1, False)
    assert r.status == "error" and r.message != NOT_INSTALLED and "Graded - part 09.zip" in r.message
    assert fake.calls == []


def test_a_matching_hash_runs(tmp_path):
    zip_file = a_zip(tmp_path)
    fake = FakeRun(cli_output())
    r = driver(fake).upload_zip(INFO, zip_file, 6, False, sha256=claude_driver.upload_log.file_hash(zip_file))
    assert r.status == "imported" and len(fake.calls) == 1


# ---------- download: the parts script in the grading page ----------
def test_download_runs_the_parts_script_on_the_grading_page_without_tools():
    run = FakeRun(cli_output({"status": "started", "users": 561, "parts": 15, "message": "the download started"}))
    out = driver(run).download(INFO)
    assert out == {"status": "started", "message": "the download started", "users": 561, "parts": 15}
    (cmd, kwargs), = run.calls
    prompt = cmd[-1]
    assert GRADING_URL.format(id="3438636") in prompt and INFO["title"] in prompt
    assert "action=downloadall" not in prompt  # Moodle cuts the one big ZIP: never asked for any more
    script = prompt[prompt.index("The script:"):]
    assert 'const ID = "3438636";' in script and "__ASSIGNMENT_ID__" not in script
    assert "downloadselected" in script
    assert cmd[cmd.index("--tools") + 1] == ""  # no built-in tools: nothing to read or write
    assert "--chrome" in cmd and kwargs["stdin"] == subprocess.DEVNULL
    assert run.seen == [{}]  # an empty folder of its own


@pytest.mark.parametrize("answer, status", [
    ({"status": "needs_login", "message": ""}, "needs_login"),
    ({"status": "imported", "message": "?"}, "error"),
])
def test_download_reports_what_went_wrong(answer, status):
    out = driver(FakeRun(cli_output(answer))).download(INFO)
    assert out["status"] == status and out["message"]


def test_download_never_raises():
    out = driver(FakeRun(raises=subprocess.TimeoutExpired("claude", 300))).download(INFO)
    assert out["status"] == "error" and "דקות" in out["message"]
    assert driver(FakeRun()).download({"id": "1; rm"})["status"] == "error"  # an id that is not digits never reaches the prompt


def test_every_prompt_renews_an_expired_session_before_giving_up(tmp_path):
    """BGU Moodle shows "404 Not Found" for an expired session; the home page signs Chrome in again (2026-10-23)."""
    info = {"id": "3438636", "title": "הגשה 0"}
    prompts = [
        claude_driver.render_prompt(info, tmp_path / "a.zip", 3, dry_run=False),
        claude_driver.CHECK_PROMPT.format(grading_url="G", home_url=claude_driver.HOME_URL),
        claude_driver.download_prompt(info),
    ]
    for prompt in prompts:
        assert "404 Not Found" in prompt
        assert prompt.count(claude_driver.HOME_URL) >= 2  # allowed, and what to open
        assert "{grading_url}" not in prompt and "{home_url}" not in prompt and "{give_up}" not in prompt


def test_download_prompt_holds_the_script_with_its_hash():
    """The page runs the script only if its SHA-256 matches: a copying mistake by Claude fails before any download."""
    import hashlib
    script, sha = claude_driver.parts_script("3438636")
    assert "`" not in script and "${" not in script  # it goes into String.raw
    assert hashlib.sha256(script.encode("utf-8")).hexdigest() == sha
    assert not any(line.lstrip().startswith("//") for line in script.split("\n"))  # less for Claude to copy
    prompt = claude_driver.download_prompt(INFO)
    assert "String.raw`" + script + "`" in prompt and f'H !== "{sha}"' in prompt
    assert prompt.rstrip().endswith("await (0, eval)(T);")


def test_the_parts_script_asks_only_for_what_changed_since():
    """A re-pull asks Moodle only for students whose submission changed since the last pull (0 = everyone)."""
    everyone, _ = claude_driver.parts_script("3438636")
    assert 'const SINCE = Number("0");' in everyone and "__SINCE__" not in everyone
    changed, sha = claude_driver.parts_script("3438636", 1761200000000)
    assert 'const SINCE = Number("1761200000000");' in changed
    prompt = claude_driver.download_prompt({**INFO, "since": 1761200000000})
    assert f'H !== "{sha}"' in prompt and '"parts" is 0 when no submission changed' in prompt


class FakeTasks:
    def __init__(self, out):
        self.out, self.calls = out, []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=self.out)


def test_closed_chrome_is_opened_on_moodle(monkeypatch, tmp_path):
    exe = tmp_path / "chrome.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(claude_driver.os, "name", "nt")
    monkeypatch.setattr(claude_driver, "CHROME_PATHS", (str(exe),))
    opened, slept = [], []
    popen = lambda cmd, **k: opened.append(cmd)
    assert claude_driver.open_chrome(FakeTasks("INFO: No tasks are running"), popen, slept.append) is True
    assert opened == [[str(exe), claude_driver.HOME_URL]] and slept == [claude_driver.CHROME_START_S]
    opened.clear()
    assert claude_driver.open_chrome(FakeTasks("chrome.exe  1234 Console"), popen, slept.append) is False
    assert opened == []  # already open: nothing to do
