"""Who imports what, read from the code itself (ast: nothing is imported or run).

Used by tests/test_modularity.py (the rules below hold) and by tools/extract_skill.py (which files a part needs).
The rules are explained in docs/Modularity.md.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The parts, bottom first. A part may use only parts that come before it, never one after it: so there is no cycle,
# and a part can be taken out (to a skill) with only what is before it.
LAYERS = ["moodle", "activity_log", "copying", "grading", "stats", "datastore", "dashboard"]

# The core: the shared folder's names and rules, which every part may use and which a part taken out to a skill takes
# with it. It lives in moodle/ next to paths.py, and it uses nothing outside itself (not even the rest of moodle/).
CORE = ["moodle", "moodle.paths", "moodle.settings", "moodle.shared_folder", "moodle.atomic", "moodle.schema",
        "moodle.grades", "moodle.claims", "moodle.lock", "moodle.claude_code"]

# Files that only keep an old import name working (`from dashboard import shared_folder`): the module itself moved
ALIASES = {"dashboard.shared_folder": "moodle.shared_folder", "dashboard.settings": "moodle.settings",
           "datastore.atomic": "moodle.atomic", "datastore.schema": "moodle.schema"}


@dataclass(frozen=True)
class Use:
    """One name a file takes from another module: `module` (dotted) and `name` in it ("" = the module itself)."""
    file: str
    line: int
    module: str
    name: str


def module_name(path: Path) -> str:
    rel = path.resolve().relative_to(REPO).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def module_file(name: str) -> Path | None:
    """moodle.paths -> moodle/paths.py, moodle -> moodle/__init__.py; None when it is not in this repo."""
    base = REPO.joinpath(*name.split("."))
    for p in (base.with_suffix(".py"), base / "__init__.py"):
        if p.is_file():
            return p
    return None


def is_package(name: str) -> bool:
    return (REPO.joinpath(*name.split(".")) / "__init__.py").is_file()


def part_of(name: str) -> str:
    return name.split(".")[0]


def part_files(part: str) -> list[Path]:
    return sorted((REPO / part).glob("*.py"))


def _absolute(module: str | None, level: int, here: str, here_is_package: bool) -> str:
    if not level:
        return module or ""
    base = here.split(".") if here_is_package else here.split(".")[:-1]
    base = base[: len(base) - (level - 1)]
    return ".".join(base + ([module] if module else []))


def imports(path: Path) -> list[Use]:
    """Every import in the file, at the top or inside a function, as absolute names.

    `from moodle import paths` is a use of the module moodle.paths; `from moodle.grades import read` a use of `read`
    in moodle.grades. Names of the standard library and of packages from pip come back too; callers keep what is ours.
    """
    here = module_name(path)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[Use] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [Use(str(path), node.lineno, a.name, "") for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = _absolute(node.module, node.level, here, path.name == "__init__.py")
            for a in node.names:
                sub = f"{base}.{a.name}" if base else a.name
                if module_file(sub) is not None:
                    out.append(Use(str(path), node.lineno, sub, ""))
                else:
                    out.append(Use(str(path), node.lineno, base, a.name))
    return out


def ours(name: str) -> bool:
    return part_of(name) in LAYERS and module_file(name) is not None


def uses(path: Path) -> list[Use]:
    """The names this file uses from other modules of the repo: every `from X import name`, and every `alias.name`
    (or `alias.sub.name`) where alias came from an import. That is what the modularity test compares to the
    INTERFACE that each part declares."""
    here = module_name(path)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    alias: dict[str, str] = {}
    out: list[Use] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if ours(a.name):
                    alias[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            base = _absolute(node.module, node.level, here, path.name == "__init__.py")
            for a in node.names:
                sub = f"{base}.{a.name}" if base else a.name
                if module_file(sub) is not None and ours(sub):
                    alias[a.asname or a.name] = sub
                elif ours(base):
                    out.append(Use(str(path), node.lineno, base, a.name))
    inner = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Attribute)}  # a.b in a.b.c: only the whole
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or id(node) in inner:
            continue
        chain, cur = [], node
        while isinstance(cur, ast.Attribute):
            chain.append(cur.attr)
            cur = cur.value
        if not isinstance(cur, ast.Name) or cur.id not in alias:
            continue
        chain.reverse()
        mod = alias[cur.id]
        # walk down through submodules: stats.compute.slot is `slot` in stats.compute
        while chain and module_file(f"{mod}.{chain[0]}") is not None and len(chain) > 1:
            mod = f"{mod}.{chain.pop(0)}"
        out.append(Use(str(path), node.lineno, mod, chain[0]))
    for name, mod in alias.items():
        out.append(Use(str(path), 0, mod, ""))
    return out


def closure(start: list[str]) -> set[str]:
    """Every module of this repo that these modules need to run, following imports (also those inside functions),
    and the packages they sit in (importing moodle.paths runs moodle/__init__.py first)."""
    todo, seen = list(start), set()
    while todo:
        m = todo.pop()
        if m in seen or module_file(m) is None:
            continue
        seen.add(m)
        parts = m.split(".")
        todo += [".".join(parts[:i]) for i in range(1, len(parts))]
        if m in ALIASES:
            todo.append(ALIASES[m])
        todo += [u.module for u in imports(module_file(m)) if ours(u.module)]
    return seen
