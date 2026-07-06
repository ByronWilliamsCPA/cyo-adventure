"""CLI: validate and import a filled story JSON into the store.

Usage:
    uv run python -m cyo_adventure.generation.import_cli <path> --family <family-uuid> [--model <model-id>]
    uv run python -m cyo_adventure.generation.import_cli <path> --job <job-uuid> [--model <model-id>]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from cyo_adventure.core.database import get_session
from cyo_adventure.core.exceptions import ProjectBaseError
from cyo_adventure.generation.import_story import (
    ImportRequest,
    import_filled_story,
    resume_manual_fill,
)


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the import CLI argument parser.

    Returns:
        Configured argument parser for the import command.
    """
    parser = argparse.ArgumentParser(
        description="Import a filled story into the store."
    )
    parser.add_argument("path", help="Path to the filled story JSON.")
    parser.add_argument(
        "--family", default=None, help="Owning family UUID (ignored with --job)."
    )
    parser.add_argument("--model", default=None, help="Model id to record.")
    parser.add_argument(
        "--job", default=None, help="Resume this awaiting_manual_fill job by id."
    )
    return parser


async def _run(
    blob: dict[str, object],
    family_id: uuid.UUID | None,
    model: str | None,
    job_id: uuid.UUID | None,
) -> tuple[str, str | None]:
    """Validate and persist a filled story blob, or resume a parked job.

    Args:
        blob: The filled Storybook JSON already loaded from disk.
        family_id: Owning family UUID (parsed by the caller). Ignored when
            job_id is given, since the job's concept already carries it.
        model: Optional model identifier to record.
        job_id: When given, resume this "awaiting_manual_fill" job instead of
            a standalone import (see import_story.py::resume_manual_fill).

    Returns:
        A ``(story_id, status)`` pair. For a resumed job, ``status`` is the
        job's final status (``"passed"`` or ``"needs_review"``); for a
        standalone import it is ``None`` (there is no job row to downgrade).

    Raises:
        ProjectBaseError: Propagated from the validation gate, the moderation
            pipeline, or (job_id path only) job-state validation.
    """
    async with get_session() as session:
        if job_id is not None:
            return await resume_manual_fill(session, job_id, blob, model=model)
        assert family_id is not None  # guaranteed by main()'s argument check
        request = ImportRequest(blob=blob, family_id=family_id, model=model)
        story_id = await import_filled_story(session, request)
        await session.commit()
        return story_id, None


def _load_blob(path: str) -> dict[str, object] | None:
    """Read and parse the filled story JSON at path, guarding path traversal.

    Args:
        path: The raw path argument from the CLI.

    Returns:
        The parsed JSON object, or None if any step failed (an error message
        has already been written to stderr in that case).
    """
    # Resolve to canonical path and reject traversal outside the working
    # directory. Required because this CLI can be invoked by an LLM agent
    # (OWASP LLM07): a faulty or adversarial path like ../../etc/passwd must
    # not reach the filesystem read.
    cwd = Path.cwd()
    resolved = Path(path).resolve()
    # Traversal check and file read are separated so their errors do not
    # conflate: relative_to raises ValueError on an out-of-tree path, while
    # read_text raises OSError (missing/unreadable) or UnicodeDecodeError (a
    # ValueError subclass) on a non-UTF-8 file. A single broad catch would
    # mislabel a decode error as a traversal rejection.
    try:
        resolved.relative_to(cwd)
    except ValueError:
        sys.stderr.write(f"error: {path} resolves outside the working directory\n")
        return None
    try:
        raw = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write(f"error: cannot read {path}: {exc}\n")
        return None
    try:
        raw_blob = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"error: invalid JSON in {path}: {exc}\n")
        return None
    if not isinstance(raw_blob, dict):
        sys.stderr.write(
            f"error: expected a JSON object in {path}, got {type(raw_blob).__name__}\n"
        )
        return None
    return raw_blob


def _parse_optional_uuid(label: str, value: str | None) -> uuid.UUID | None:
    """Parse an optional UUID CLI argument.

    Args:
        label: Human-readable argument name for the error message (e.g.
            "job" or "family").
        value: The raw string value from argparse, or None if not given.

    Returns:
        The parsed UUID, or None if value was None.

    Raises:
        ValueError: If value is given but is not a valid UUID. The message is
            ready to write to stderr as-is.
    """
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        msg = f"error: invalid {label} UUID: {value}\n"
        raise ValueError(msg) from exc


def main(argv: list[str] | None = None) -> int:
    """Parse args, import the story, and print the resulting story id.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Exit code: 0 on success, 1 on any handled failure.
    """
    args = build_arg_parser().parse_args(argv)
    # Bind argparse Namespace attributes (typed Any) to explicit locals so the
    # rest of main stays strictly typed.
    path: str = args.path
    family: str | None = args.family
    model: str | None = args.model
    job: str | None = args.job
    if job is None and family is None:
        sys.stderr.write("error: --family is required unless --job is given\n")
        return 1
    blob = _load_blob(path)
    if blob is None:
        return 1
    try:
        job_id = _parse_optional_uuid("job", job)
        family_id = _parse_optional_uuid("family", family)
    except ValueError as exc:
        sys.stderr.write(str(exc))
        return 1
    # #CRITICAL: data-integrity: ProjectBaseError (not a bare ValueError) covers
    # both the validation gate's ValidationError and any exception the
    # moderation pipeline raises after a successful persist (e.g.
    # ResourceNotFoundError, a review-backend ExternalServiceError); the UUID
    # ValueError catch above does not overlap with it. core/database.py's
    # get_session() closes (and thus rolls back) the session on any exception
    # exiting the `async with` block in _run, so a moderation failure here
    # cannot leave a half-committed row.
    # #VERIFY: test_arg_parser_* cover parsing; gate and moderation failures
    # both map to exit 1.
    try:
        story_id, status = asyncio.run(_run(blob, family_id, model, job_id))
    except ProjectBaseError as exc:
        sys.stderr.write(f"import failed: {exc}\n")
        return 1
    # Surface a Stage 1 fidelity downgrade so the operator can tell a clean
    # pass from a fill parked for admin review; a bare story id looked
    # identical for both outcomes.
    if status is not None and status != "passed":
        sys.stdout.write(f"imported {story_id} (job status: {status})\n")
    else:
        sys.stdout.write(f"imported {story_id}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
