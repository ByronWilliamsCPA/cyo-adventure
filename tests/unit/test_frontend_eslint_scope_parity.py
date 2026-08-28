"""Contract test: the `frontend-eslint` pre-commit hook's scope matches `npm run lint`.

The hook's own comment block says the two scopes must be kept in step, because
a file the npm `lint` script reaches in CI (and therefore the ESLint SAST
floor: eslint-plugin-security, eslint-plugin-no-unsanitized) but the hook does
not reach at commit time is unlinted until CI, not at commit time. That
`#VERIFY` was prose asking a human to remember, and it already failed twice:
`design-system/` was the first drift and `e2e-usersim/` was the second (this
branch added code to `e2e-usersim/` all day while the hook's `files:` regex
did not cover it).

This test derives both scopes from their real sources rather than comparing
two hand-maintained lists, which would just move the drift somewhere else:

* The hook scope comes from compiling `.pre-commit-config.yaml`'s actual
  `files:`/`exclude:` regexes and applying them to the real set of
  git-tracked files under `frontend/`.
* The npm scope comes from parsing the actual `lint` script in
  `frontend/package.json`, expanding its brace globs (`{ts,tsx}`), and
  globbing the real filesystem under `frontend/`.

Both sides drop `src/client/`: it is `@hey-api/openapi-ts` generated output
that both the hook's `exclude:` line and `eslint.config.js`'s top-level
`ignores` deliberately skip, so it is not part of either tool's *effective*
lint scope even though the raw `src/**/*.{ts,tsx}` glob text would otherwise
include it.

Ceiling: this proves the two configured *scopes* match on the files that
exist today. It does not prove ESLint would actually flag a real problem in a
newly-covered file; that is `npm run lint` itself, not this test.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"
PRE_COMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"
PACKAGE_JSON = FRONTEND_DIR / "package.json"
HOOK_ID = "frontend-eslint"

# Both the ESLint flat config (`eslint.config.js`'s top-level `ignores`) and
# the pre-commit hook's own `exclude:` line drop the generated API client, so
# this test drops it from both derived scopes too. Otherwise the raw
# `src/**/*.{ts,tsx}` glob text would make the npm side look like it covers
# client/ when neither tool actually lints it.
GENERATED_CLIENT_PREFIX = "src/client/"


def _load_hook() -> dict[str, Any]:
    """Return the `frontend-eslint` local hook's config mapping.

    Returns:
        The hook's mapping (`files`, `exclude`, etc.) as parsed YAML.

    Raises:
        AssertionError: If no `local` repo defines a hook with this id.
    """
    yaml = YAML(typ="safe")
    config = yaml.load(PRE_COMMIT_CONFIG)
    for repo in config["repos"]:
        if repo.get("repo") != "local":
            continue
        for hook in repo.get("hooks", []):
            if hook.get("id") == HOOK_ID:
                return hook
    raise AssertionError(f"hook {HOOK_ID!r} not found in {PRE_COMMIT_CONFIG}")


def _hook_scope() -> set[str]:
    """Derive the set of frontend-relative paths the hook actually matches.

    Returns:
        Paths (relative to `frontend/`) that satisfy the hook's `files:`
        regex and do not satisfy its `exclude:` regex, restricted to files
        git actually tracks so untracked scratch files cannot skew the
        comparison.
    """
    hook = _load_hook()
    files_re = re.compile(hook["files"])
    exclude_re = re.compile(hook["exclude"]) if hook.get("exclude") else None
    git = shutil.which("git")
    assert git is not None, "git must be on PATH to derive the tracked file list"
    tracked = subprocess.run(
        [git, "-C", str(REPO_ROOT), "ls-files", "frontend"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    scope: set[str] = set()
    for path in tracked:
        if not files_re.match(path):
            continue
        if exclude_re is not None and exclude_re.match(path):
            continue
        relative = path[len("frontend/") :]
        if relative.startswith(GENERATED_CLIENT_PREFIX):
            continue
        scope.add(relative)
    return scope


_BRACE_RE = re.compile(r"\{([^{}]+)\}")


def _expand_braces(pattern: str) -> list[str]:
    """Expand one `{a,b}` brace group in a glob pattern into literal variants.

    Args:
        pattern: A glob pattern, e.g. `"src/**/*.{ts,tsx}"`.

    Returns:
        The pattern with every brace group expanded, e.g.
        `["src/**/*.ts", "src/**/*.tsx"]`. A pattern with no brace group is
        returned unchanged as a single-element list.
    """
    match = _BRACE_RE.search(pattern)
    if not match:
        return [pattern]
    prefix, suffix = pattern[: match.start()], pattern[match.end() :]
    candidates = [f"{prefix}{option}{suffix}" for option in match.group(1).split(",")]
    expanded: list[str] = []
    for candidate in candidates:
        expanded.extend(_expand_braces(candidate))
    return expanded


def _npm_lint_globs() -> list[str]:
    """Extract the quoted glob arguments from `frontend/package.json`'s `lint` script.

    Returns:
        The glob strings in the order they appear in the `lint` script
        (flags like `--max-warnings=0` are unquoted and excluded).
    """
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    lint_script = package["scripts"]["lint"]
    return re.findall(r'"([^"]+)"', lint_script)


def _npm_scope() -> set[str]:
    """Derive the set of frontend-relative paths `npm run lint` actually globs.

    Returns:
        Paths (relative to `frontend/`) matched by expanding and globbing
        every quoted argument in the `lint` script, restricted to real files
        on disk.
    """
    scope: set[str] = set()
    for glob_pattern in _npm_lint_globs():
        for expanded in _expand_braces(glob_pattern):
            for match in FRONTEND_DIR.glob(expanded):
                if not match.is_file():
                    continue
                relative = match.relative_to(FRONTEND_DIR).as_posix()
                if relative.startswith(GENERATED_CLIENT_PREFIX):
                    continue
                scope.add(relative)
    return scope


def test_npm_lint_scope_is_not_vacuous() -> None:
    """Guard against a vacuous pass.

    If YAML/JSON parsing or glob expansion silently broke and both derived
    scopes came back empty, the equality checks below would pass having
    compared nothing. Pin a floor derived from the real tree instead.
    """
    assert len(_npm_scope()) > 20
    assert len(_hook_scope()) > 20


def test_npm_lint_scope_has_no_paths_the_precommit_hook_misses() -> None:
    """Every path `npm run lint` reaches is also reached by the pre-commit hook.

    A red run here names the exact files the hook's `files:` regex is missing,
    the failure mode `e2e-usersim/` produced.
    """
    missing = sorted(_npm_scope() - _hook_scope())
    assert not missing, (
        "npm run lint covers paths the frontend-eslint pre-commit hook does "
        f"not check at commit time: {missing}"
    )


def test_precommit_hook_has_no_paths_npm_lint_skips() -> None:
    """The pre-commit hook does not check anything `npm run lint` would skip.

    This is the same drift pointing the other way: a hook that checks paths
    npm's `lint` script no longer covers gives a false sense that CI and
    commit-time agree.
    """
    extra = sorted(_hook_scope() - _npm_scope())
    assert not extra, (
        "frontend-eslint pre-commit hook checks paths npm run lint does not "
        f"cover: {extra}"
    )
