"""
LAAP AGI — Heartbeat Daemon

Periodically publishes agent presence to both AgentRegistry and EventBus.
Designed to run as a background thread or standalone process.

Usage:
    python -m laap.agi.heartbeat_daemon --agent-id my_agent_001
    python -m laap.agi.heartbeat_daemon --agent-id my_agent_001 --interval 30
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import NoReturn

# Ensure LAAP package is importable
_laap_root = os.environ.get("LAAP_ROOT")
if _laap_root is None:
    # Infer project root from this file location (laap/agi/heartbeat_daemon.py)
    _laap_root = str(Path(__file__).resolve().parents[2])
if _laap_root not in sys.path:
    sys.path.insert(0, _laap_root)

from laap.agi.multi_agent import heartbeat_cycle

logger = logging.getLogger("laap.agi.heartbeat_daemon")


def run_daemon(
    agent_id: str,
    interval: int = 15,
    registry_path: str = "",
    events_path: str = "",
) -> NoReturn:
    """Run an infinite heartbeat loop.

    Every *interval* seconds calls :func:`heartbeat_cycle`, which updates the
    AgentRegistry timestamp and publishes an ``AGENT_HEARTBEAT`` event on the
    EventBus.  Catches and logs transient errors without crashing.
    """
    cycle_count = 0
    logger.info(
        "Heartbeat daemon started — agent=%s interval=%ds",
        agent_id,
        interval,
    )

    while True:
        try:
            result = heartbeat_cycle(agent_id, registry_path, events_path)
            cycle_count += 1
            if result["registry_ok"]:
                logger.debug(
                    "Cycle %d — registry=OK event=%s",
                    cycle_count,
                    result.get("event_id", "N/A"),
                )
            else:
                logger.warning("Cycle %d — registry heartbeat failed", cycle_count)
        except Exception as exc:
            logger.error("Cycle %d — unhandled error: %s", cycle_count, exc)

        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LAAP AGI Heartbeat Daemon",
    )
    parser.add_argument(
        "--agent-id",
        required=True,
        help="Unique agent identifier (e.g. 'agent_coder_01')",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Heartbeat interval in seconds (default: 15)",
    )
    parser.add_argument(
        "--registry-path",
        default="",
        help="Path to the AgentRegistry JSON file (default: LAAP_ROOT/.agent_registry.json)",
    )
    parser.add_argument(
        "--events-path",
        default="",
        help="Path to the EventBus JSON file (default: LAAP_ROOT/.agent_events.json)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    if args.interval < 5:
        logger.warning("Interval < 5s may cause excessive I/O — overriding to 5")
        args.interval = 5

    try:
        run_daemon(
            agent_id=args.agent_id,
            interval=args.interval,
            registry_path=args.registry_path,
            events_path=args.events_path,
        )
    except KeyboardInterrupt:
        logger.info("Heartbeat daemon stopped by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
