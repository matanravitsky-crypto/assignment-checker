"""Run the dashboard on the fictional demo folder, with a Moodle that is only simulated.

    python -m tests.serve_demo [--port 8765]

Builds data/demo-root (see make_demo_root.py) if it is missing, then starts `python -m dashboard serve --no-open`
with ASSIGNMENT_CHECKER_ROOT pointing at it, MOODLE_DRIVER=simulate and MOODLE_READY=simulate. All three are set here,
whatever the environment says, so this can never reach the real shared folder or start `claude`, an installer or a login.
With MOODLE_READY=simulate the site's "is this computer ready" check starts as "not logged in", and about 2 s after
the site asks for the login it says all is ready (restart the server to see it again).
Paths come from this file's place, so it works from any working directory.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dashboard import __main__ as dashboard_cli
from tests import make_demo_root

REPO = Path(__file__).resolve().parent.parent
DEMO_ROOT = REPO / "data" / "demo-root"


def main(argv: list[str] | None = None) -> int:
    if not DEMO_ROOT.is_dir():
        make_demo_root.build(DEMO_ROOT)
    os.environ["ASSIGNMENT_CHECKER_ROOT"] = str(DEMO_ROOT)
    os.environ["MOODLE_DRIVER"] = "simulate"
    os.environ["MOODLE_READY"] = "simulate"  # the readiness check pretends: login "takes" ~2 s, then all is ready
    return dashboard_cli.main(["serve", "--no-open", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    sys.exit(main())
