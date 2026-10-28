"""Command line interface."""

from __future__ import annotations

import argparse
import logging
import re
import sys

from .config import ConfigError, load_config
from .pipeline import local_day, probe, run_monitor, send_test
from .state import StateError

log = logging.getLogger("bcrp_monitor")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bcrp-monitor")
    parser.add_argument("--dry-run", action="store_true", help="send nothing")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--probe",
        nargs="?",
        const="today",
        metavar="YYYYMMDD",
        help="inspect one gazette day",
    )
    actions.add_argument("--test", action="store_true", help="send a test message")
    parser.add_argument(
        "--reset-state", action="store_true", help="ignore the current state"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _setup_logging()
    try:
        config = load_config()
        if args.test:
            return send_test(config, args.dry_run)
        if args.probe:
            day = local_day(config) if args.probe == "today" else str(args.probe)
            if not re.fullmatch(r"\d{8}", day):
                log.error("Probe date must use YYYYMMDD")
                return 2
            return probe(config, day, args.dry_run)
        return run_monitor(config, args.dry_run, args.reset_state)
    except (ConfigError, StateError) as exc:
        log.error("%s", exc)
        return 2
    except Exception:
        log.exception("Unhandled failure")
        return 1


if __name__ == "__main__":
    sys.exit(main())
