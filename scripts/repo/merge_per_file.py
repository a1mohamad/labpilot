#!/usr/bin/env python3
"""Move the current branch onto main: ONE file per commit, ONE push per commit.

Run it inside the repository, on the branch you want to move:

    python merge_per_file.py --dry-run          # show the plan, change nothing
    python merge_per_file.py                    # show the plan, ask, then do it
    python merge_per_file.py --yes --test "pytest tests/unit tests/api -q"

What it does
  1. Checks that the tree is clean and that main holds no work the branch lacks.
  2. Lists the files that differ between main and the branch.
  3. Orders them. Sources go in import order, each test goes right after the last
     source it needs, documents go last (DETAILS.md before CLAUDE.md).
  4. For each file: copy it from the branch, commit ONLY that file, push.
  5. At the end it checks that main and the branch are identical.

If it stops (network, a failed hook, Ctrl-C), run it again. Files that are
already equal on main are not listed, so it continues where it stopped.

Optional: --messages FILE with one line per file, "path|commit message".
Without it the messages are plain ("feat: add x.py", "test: update y.py").
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
import time

DOCS_FIRST = ["DETAILS.md", "CLAUDE.md"]  # the fuller document goes first


def git(*args: str, check: bool = True) -> str:
    done = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and done.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed:\n{done.stdout}{done.stderr}")
    return done.stdout.strip()


def git_ok(*args: str) -> bool:
    return subprocess.run(["git", *args], capture_output=True).returncode == 0


def is_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (
        path.startswith(("tests/", "test/"))
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


# ---------------------------------------------------------------- the file list
def changed_files(target: str, branch: str) -> dict[str, str]:
    """path -> A (added), M (modified) or D (deleted), main compared with the branch."""
    parts = git("diff", "--name-status", "--no-renames", "-z", target, branch).split(
        "\0"
    )
    return {parts[i + 1]: parts[i][0] for i in range(0, len(parts) - 1, 2)}


def work_only_on_target(target: str, branch: str, files: dict[str, str]) -> list[str]:
    """Files main changed that are NOT an older version of the branch's file.

    Copying the branch over such a file would throw main's own work away.
    """
    base = git("merge-base", target, branch)
    touched = set(git("diff", "--name-only", "-z", base, target).split("\0")) - {""}
    unique = []
    for path in sorted(touched & set(files)):
        on_target = git("rev-parse", f"{target}:{path}", check=False)
        seen = [
            git("rev-parse", f"{commit}:{path}", check=False)
            for commit in git("log", "--format=%H", branch, "--", path).split()
        ]
        if not on_target or on_target not in seen:
            unique.append(path)
    return unique


# ------------------------------------------------------------------- the order
def module_files(dotted: str) -> list[str]:
    base = dotted.replace(".", "/")
    return [
        f"{base}.py",
        f"{base}/__init__.py",
        f"src/{base}.py",
        f"src/{base}/__init__.py",
    ]


def absolute_name(module: str, level: int, path: str) -> str:
    if level == 0:
        return module
    folder = path.split("/")[:-1]
    folder = folder[: len(folder) - (level - 1)] if level > 1 else folder
    prefix = ".".join(part for part in folder if part != "src")
    return ".".join(part for part in (prefix, module) if part)


def imports_of(
    path: str, branch: str, tree: set[str], changed_py: set[str]
) -> set[str]:
    """The changed python files this file may import (a package: all of its files)."""
    try:
        parsed = ast.parse(git("show", f"{branch}:{path}"))
    except SyntaxError:
        return set()

    found: set[str] = set()
    for node in ast.walk(parsed):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = absolute_name(node.module or "", node.level, path)
            names = [base] + [
                f"{base}.{alias.name}" if base else alias.name for alias in node.names
            ]
        for name in filter(None, names):
            file = next((c for c in module_files(name) if c in tree), None)
            if file is None:
                continue
            if file in changed_py:
                found.add(file)
            if file.endswith("/__init__.py"):
                package = file[: -len("__init__.py")]
                found |= {p for p in changed_py if p.startswith(package)}
    return found


def order_files(files: dict[str, str], branch: str) -> list[str]:
    tree = set(git("ls-tree", "-r", "--name-only", "-z", branch).split("\0")) - {""}
    alive = {p for p, status in files.items() if status != "D"}
    docs = sorted(
        (p for p in alive if p.endswith(".md")),
        key=lambda p: (DOCS_FIRST.index(p) if p in DOCS_FIRST else len(DOCS_FIRST), p),
    )
    tests = sorted(p for p in alive if is_test(p) and p not in docs)
    sources = sorted(alive - set(docs) - set(tests))
    py_sources = [p for p in sources if p.endswith(".py")]
    other_sources = [p for p in sources if not p.endswith(".py")]

    graph = {p: imports_of(p, branch, tree, set(py_sources)) for p in py_sources}
    ordered: list[str] = []
    done: set[str] = set()
    remaining = list(py_sources)
    while remaining:
        ready = [p for p in remaining if graph[p] - {p} <= done] or [remaining[0]]
        ordered += ready
        done |= set(ready)
        remaining = [p for p in remaining if p not in done]
    ordered += other_sources
    position = {p: i for i, p in enumerate(ordered)}

    def closure(start: set[str]) -> set[str]:
        seen: set[str] = set()
        todo = list(start)
        while todo:
            item = todo.pop()
            if item not in seen:
                seen.add(item)
                todo += graph.get(item, ())
        return seen

    after: dict[int, list[str]] = {}
    loose: list[str] = []
    for test in tests:
        needs = closure(imports_of(test, branch, tree, set(py_sources)))
        text = git("show", f"{branch}:{test}")
        needs |= {p for p in other_sources if p in text or p.rsplit("/", 1)[-1] in text}
        if needs:
            after.setdefault(max(position[n] for n in needs), []).append(test)
        else:
            loose.append(test)

    deleted = sorted(p for p, status in files.items() if status == "D")
    final = [p for p in deleted if is_test(p)]
    for index, source in enumerate(ordered):
        final.append(source)
        final += after.get(index, [])
    final += loose
    final += [p for p in deleted if not is_test(p)]
    return final + docs


# ------------------------------------------------------------------ the doing
def auto_message(path: str, status: str) -> str:
    if status == "D":
        return f"chore: remove {path}"
    if is_test(path):
        kind = "test"
    elif path.endswith(".md"):
        kind = "docs"
    elif path.startswith(".github/"):
        kind = "ci"
    elif path.startswith("scripts/"):
        kind = "chore"
    else:
        kind = "feat" if status == "A" else "chore"
    verb = "add" if status == "A" else "update"
    return f"{kind}: {verb} {path}"


def read_messages(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    with open(path, encoding="utf-8") as handle:
        return dict(line.rstrip("\n").split("|", 1) for line in handle if "|" in line)


def push(remote: str, target: str, retries: int) -> bool:
    for attempt in range(1, retries + 1):
        if subprocess.run(["git", "push", "-q", remote, target]).returncode == 0:
            return True
        print(f"    push try {attempt} failed, waiting 10 s")
        time.sleep(10)
        # A dropped connection can come AFTER the server took the push: look.
        if git("ls-remote", remote, target, check=False).split("\t")[0] == git(
            "rev-parse", "HEAD"
        ):
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--target", default="main", help="the branch to move work onto")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--messages", help='file with "path|commit message" lines')
    parser.add_argument(
        "--trailer", action="append", default=[], help="a line added to every message"
    )
    parser.add_argument(
        "--test", help="a command to run after every commit (its result is logged)"
    )
    parser.add_argument(
        "--stop-on-red",
        action="store_true",
        help="stop BEFORE the push when --test fails",
    )
    parser.add_argument(
        "--retries", type=int, default=6, help="push tries for each commit"
    )
    parser.add_argument(
        "--limit", type=int, help="do only the first N files, then stop"
    )
    parser.add_argument(
        "--write-messages",
        help="write the plan as a messages file to edit, then stop",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true", help="do not ask before starting")
    args = parser.parse_args()

    git("rev-parse", "--show-toplevel")
    branch = git("branch", "--show-current")
    if not branch:
        sys.exit("You are on a detached HEAD. Switch to the branch you want to move.")
    if branch == args.target:
        sys.exit(f"You are on {args.target}. Switch to the branch you want to move.")
    if git("status", "--porcelain"):
        sys.exit("The working tree is not clean. Commit or stash first.")

    git("fetch", "-q", args.remote)
    remote_ref = f"{args.remote}/{args.target}"
    if not git_ok("merge-base", "--is-ancestor", args.target, remote_ref):
        sys.exit(
            f"Local {args.target} has commits that {remote_ref} does not. "
            "Push or reset them first."
        )

    files = changed_files(remote_ref, branch)
    if not files:
        sys.exit(f"{args.target} already equals {branch}. Nothing to do.")
    unique = work_only_on_target(remote_ref, branch, files)
    if unique:
        sys.exit(
            f"{args.target} has work in these files that {branch} lacks:\n  "
            + "\n  ".join(unique)
            + f"\nMerge {args.target} into {branch} first, "
            "or the copy would delete that work."
        )

    order = order_files(files, branch)
    messages = read_messages(args.messages)
    plan = [(p, files[p], messages.get(p) or auto_message(p, files[p])) for p in order]
    print(
        f"{len(plan)} files: {branch} -> {args.target}, one commit and one push each\n"
    )
    for number, (path, status, message) in enumerate(plan, start=1):
        print(f"  {number:3d} {status} {path:55.55s} {message}")
    if args.write_messages:
        with open(args.write_messages, "w", encoding="utf-8", newline="\n") as out:
            out.writelines(f"{path}|{message}\n" for path, _, message in plan)
        print(f"\nWrote {args.write_messages}. Edit the messages, then use --messages.")
        return
    if args.dry_run:
        return
    if (
        not args.yes
        and input(
            f"\nPush {len(plan)} commits to {args.target} one by one? [y/N] "
        ).lower()
        != "y"
    ):
        sys.exit("Stopped. Nothing was changed.")

    def stop(text: str) -> None:
        sys.exit(
            f"{text}\nTo continue: git switch {branch}, then run this script again."
        )

    git("switch", args.target)
    git("merge", "--ff-only", remote_ref)
    red: list[str] = []
    try:
        for number, (path, status, message) in enumerate(plan[: args.limit], start=1):
            if status == "D":
                git("rm", "-q", "--", path)
            else:
                git("checkout", branch, "--", path)
            command = ["git", "commit", "-q", "-m", message]
            for line in args.trailer:
                command += ["-m", line]
            done = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if done.returncode != 0:
                stop(f"Commit {number} ({path}) failed:\n{done.stdout}{done.stderr}")
            if len(git("show", "--name-only", "--format=", "HEAD").splitlines()) != 1:
                stop(f"Commit {number} holds more than one file. Stopped.")

            note = ""
            if args.test:
                result = subprocess.run(
                    args.test,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                lines = (result.stdout.strip() or result.stderr.strip()).splitlines()
                note = f" | tests: {lines[-1] if lines else result.returncode}"
                if result.returncode != 0:
                    red.append(path)
                    if args.stop_on_red:
                        stop(
                            f"Tests are red after commit {number} ({path}). "
                            "It is NOT pushed.\n"
                            "To drop that commit: git reset --hard HEAD~1"
                            f"  (you are on {args.target})."
                        )
            if not push(args.remote, args.target, args.retries):
                stop(
                    f"Push {number} ({path}) failed. The commit is local only.\n"
                    "Run `git push` yourself when the network is back, "
                    "or drop it with: git reset --hard HEAD~1"
                )
            short = git("rev-parse", "--short", "HEAD")
            print(f"  [{number}/{len(plan)}] {short} {path}{note}")
    except KeyboardInterrupt:
        stop("\nInterrupted.")

    git("switch", branch)
    if git_ok("diff", "--quiet", args.target, branch):
        print(f"\nDone: {args.target} is identical to {branch}.")
        print(f"You are back on {branch}.")
    else:
        print(f"\nStopped early: {args.target} still differs from {branch}.")
        print("Run this script again to continue.")
    if red:
        print(
            f"Tests were red after {len(red)} commits: "
            + ", ".join(red[:8])
            + (" ..." if len(red) > 8 else "")
        )


if __name__ == "__main__":
    main()
