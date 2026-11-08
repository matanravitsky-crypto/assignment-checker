"""The public numbers board (dashboard/public_status.py): numbers only, published only when something changed."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from dashboard import actions, public_status
from tests.dashboard.helpers import COURSE, HW, NAMES


def test_the_summary_has_numbers_only(root):
    """Nothing about one submission leaves the computer: no numbers of submissions, grades, comments, files or names."""
    st = actions.state(root)
    sub = next(a for a in st["assignments"] if a.get("subs"))["subs"][0]
    text = json.dumps(public_status.summary(st), ensure_ascii=False)
    for name in NAMES.values():
        assert name not in text
    for leak in ("0001", "0002", ".pdf", "feedback", "score", "comments", "studentId", "path", "moodleId", "copying", str(root)):
        assert leak not in text, leak
    assert sub["id"] == "0001"  # the state does have them: the summary drops them


def test_the_summary_counts_each_stage(root):
    st = actions.state(root)
    a = next(a for a in st["assignments"] if a.get("subs"))
    subs = a["subs"]
    subs[0].update(status="returned", approved=True)
    subs[1].update(status="graded", review="שאלה 2 לא ברורה")
    body = public_status.summary(st)
    row = next(r for c in body["courses"] for r in c["assignments"] if r["title"] == a["title"])
    assert (row["pulled"], row["graded"], row["review"], row["approved"], row["returned"]) == (3, 2, 1, 1, 1)
    assert {"pulledAt", "gradedAt", "returnedAt", "due", "pullOwner", "returnOwner", "empty", "n"} <= set(row)
    assert all(r["empty"] and r["pulled"] == 0 for c in body["courses"] for r in c["assignments"] if r["title"] != a["title"])


class Fake:
    def __init__(self):
        self.sig, self.state_calls, self.published = "s1", 0, []
        self.now = datetime(2026, 11, 3, 22, 0)
        self.counts = {"pulled": 3}

    def state(self, root):
        self.state_calls += 1
        return {"courses": [{"id": "c0", "name": COURSE}],
                "assignments": [{"courseId": "c0", "title": HW, "subs": [{"status": "pulled"}] * self.counts["pulled"]}]}

    def publisher(self, ok=True):
        def publish(gist, text):
            self.published.append(json.loads(text))
            return ok
        return public_status.Publisher("g1", self.state, lambda root: self.sig, lambda: "מתן", publish=publish,
                                       clock=lambda: self.now)


def test_publishes_only_what_changed_and_a_heartbeat(tmp_path):
    f = Fake()
    p = f.publisher()
    assert p.tick(tmp_path) and f.published[-1]["publishedBy"] == "מתן"
    assert f.published[-1]["courses"][0]["assignments"][0]["pulled"] == 3
    f.now += timedelta(minutes=2)
    assert not p.tick(tmp_path) and f.state_calls == 1  # the folder did not change: not even the summary is built
    f.sig = "s2"  # something changed in the folder, but not the numbers (say a grading note)
    assert not p.tick(tmp_path) and len(f.published) == 1
    f.sig, f.counts["pulled"] = "s3", 4  # a pull brought one more
    assert p.tick(tmp_path) and f.published[-1]["courses"][0]["assignments"][0]["pulled"] == 4
    f.now += timedelta(seconds=public_status.HEARTBEAT_S)
    assert p.tick(tmp_path) and len(f.published) == 3  # nothing changed for an hour: published anyway, so the site sees it's alive


def test_a_failed_publish_is_tried_again(tmp_path):
    f = Fake()
    p = f.publisher(ok=False)
    assert not p.tick(tmp_path) and not p.tick(tmp_path)
    assert len(f.published) == 2  # the same signature, tried again because nothing went out


def test_publish_patches_the_gist_through_gh():
    calls = []

    class Done:
        returncode = 0

    def run(cmd, **kw):
        calls.append((cmd, kw))
        return Done()

    assert public_status.publish("abc123", '{"courses": []}', run=run, gh="gh")
    (cmd, kw), = calls
    assert cmd == ["gh", "api", "--method", "PATCH", "gists/abc123", "--input", "-"]
    assert json.loads(kw["input"].decode("utf-8")) == {"files": {"status.json": {"content": '{"courses": []}'}}}


def test_only_the_computer_with_the_gist_publishes(monkeypatch):
    monkeypatch.delenv("PUBLIC_STATUS_GIST", raising=False)
    assert public_status.start() is None
