"""Command-line entrypoint: ``python -m astraeus``.

Phase 0 (PRD v4.1 §2.3 / §16): establishes a REAL entrypoint. Before
this, ``astraeus/main.py`` was a hardcoded single-target script
(``RealDataPipeline(...).execute_full_workflow(target_name="TrES-2b")``)
with a ``sys.path.append`` hack -- not a CLI, and ``python -m astraeus``
could not work at all because ``__main__.py`` did not exist.

Scope discipline: this is deliberately minimal. There is no interactive
shell, no subcommand tree beyond ``capabilities``, no job queue, and no
server -- those belong to Phase 1+. The ``capabilities`` subcommand is
in scope because capability reporting is a Phase 0 deliverable, and it
is the fastest way to answer "will this environment fail closed?".

The command works from any current working directory: artifact paths
resolve through :mod:`astraeus.core.paths`, never relative to CWD.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from astraeus import __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="astraeus",
        description=(
            "ASTRAEUS exoplanet transit detection, vetting, and analysis "
            "engine. Scientific backends (wotan, transitleastsquares) are "
            "required for a production run: a missing backend fails closed "
            "rather than silently degrading the result."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"astraeus {__version__}",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity for the astraeus logger (default: WARNING).",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    caps = sub.add_parser(
        "capabilities",
        help="Report which scientific backends are importable, as JSON.",
        description=(
            "Report the scientific backend capability snapshot. Exit code "
            "reflects capability: 0 if every required backend is present, "
            "1 otherwise. This is the pre-flight check for a production run."
        ),
    )
    caps.add_argument(
        "--missing-is-error",
        action="store_true",
        default=True,
        help="Exit 1 when a required backend is unavailable (default).",
    )
    return parser


def _cmd_capabilities(_args: argparse.Namespace) -> int:
    from astraeus.core.capabilities import BackendId, CapabilitySnapshot

    snapshot = CapabilitySnapshot.current()
    print(json.dumps(snapshot.to_dict(), indent=2))
    missing = snapshot.missing([BackendId.WOTAN, BackendId.TLS])
    if missing:
        names = ", ".join(b.value for b in missing)
        print(
            f"astraeus: MISSING required scientific backends: {names}. "
            "A production run will fail closed; install them (see "
            "pyproject.toml [project.dependencies]).",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.getLogger("astraeus").setLevel(getattr(logging, args.log_level))

    if args.command == "capabilities":
        return _cmd_capabilities(args)

    # No subcommand given: show usage. This is the friendly default for an
    # engine whose real driver today is the Python API and the reference UI.
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
