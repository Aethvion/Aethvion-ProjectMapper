"""
project_mapper/watcher.py
Background file-change watcher for automatic incremental scans.

Polls the project directory at a configurable interval using PM's delta
engine (SHA-256 comparison). When changes are detected, waits a short
debounce window, then triggers an incremental scan — keeping the graph
fresh without agent intervention.

No extra dependencies: uses the existing delta machinery.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AutoScanner:
    """
    Daemon thread that polls for file-system changes and runs incremental scans.

    Shares a ``scan_lock`` with ``handle_pm_scan`` so manual and auto scans
    never overlap.  If the lock is held when a change is detected, the
    auto-scan cycle is skipped and retried on the next poll.
    """

    def __init__(
        self,
        project_root:  str,
        db_root:       Path,
        db_name:       str,
        writer:        Any,
        index:         Any,
        file_manifest: Any,
        scan_lock:     threading.Lock,
        poll_interval: float = 10.0,
        debounce:      float = 2.0,
    ) -> None:
        self.project_root  = project_root
        self.db_root       = db_root
        self.db_name       = db_name
        self.writer        = writer
        self.index         = index
        self.file_manifest = file_manifest
        self.scan_lock     = scan_lock
        self.poll_interval = poll_interval
        self.debounce      = debounce

        self._thread:     Optional[threading.Thread] = None
        self._stop_event: threading.Event = threading.Event()

        # Status fields — read by handle_pm_stats
        self.active:          bool            = False
        self.scan_count:      int             = 0
        self.last_check_at:   Optional[float] = None
        self.last_scan_at:    Optional[float] = None
        self.last_scan_files: int             = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self.active  = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="pm-auto-scan"
        )
        self._thread.start()
        logger.info(
            "[AutoScanner] Watching %r — poll=%.0fs  debounce=%.0fs",
            self.project_root,
            self.poll_interval,
            self.debounce,
        )

    def stop(self) -> None:
        self._stop_event.set()
        self.active = False
        if self._thread:
            self._thread.join(timeout=5.0)

    # ------------------------------------------------------------------
    # Poll loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception as exc:
                logger.warning("[AutoScanner] Poll error: %s", exc)
            # Sleep in small increments to respond to stop_event promptly
            ticks = max(1, int(self.poll_interval / 0.5))
            for _ in range(ticks):
                if self._stop_event.is_set():
                    return
                time.sleep(0.5)

    def _poll_once(self) -> None:
        from .delta import compute_delta

        self.last_check_at = time.time()
        try:
            delta = compute_delta(self.project_root, self.file_manifest)
        except Exception as exc:
            logger.debug("[AutoScanner] Delta error: %s", exc)
            return

        if not delta.has_changes:
            return

        n_changed = (
            len(delta.new_files)
            + len(delta.modified_files)
            + len(delta.deleted_files)
        )
        logger.info(
            "[AutoScanner] %d change(s) detected — debouncing %.0fs …",
            n_changed,
            self.debounce,
        )

        # Debounce: let flurries of saves settle before scanning
        ticks = max(1, int(self.debounce / 0.1))
        for _ in range(ticks):
            if self._stop_event.is_set():
                return
            time.sleep(0.1)

        if self._stop_event.is_set():
            return

        # Try to acquire the scan lock — skip if a manual scan is running
        if not self.scan_lock.acquire(blocking=False):
            logger.info("[AutoScanner] Scan lock held — skipping cycle.")
            return

        try:
            logger.info("[AutoScanner] Running incremental scan …")
            t0 = time.monotonic()
            asyncio.run(self._do_scan())
            elapsed = time.monotonic() - t0
            self.last_scan_at    = time.time()
            self.last_scan_files = n_changed
            self.scan_count     += 1
            logger.info(
                "[AutoScanner] Scan done in %.1fs (%d file(s)).",
                elapsed,
                n_changed,
            )
        except Exception as exc:
            logger.warning("[AutoScanner] Scan failed: %s", exc)
        finally:
            self.scan_lock.release()

    async def _do_scan(self) -> None:
        from .scanner import run_scan

        await run_scan(
            db_root=self.db_root,
            project_root=self.project_root,
            db_name=self.db_name,
            writer=self.writer,
            index=self.index,
            file_manifest=self.file_manifest,
            concurrency=2,
            incremental=True,
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status_dict(self) -> dict[str, Any]:
        import datetime

        def _fmt(ts: Optional[float]) -> str:
            if ts is None:
                return "never"
            return datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")

        return {
            "active":          self.active,
            "project_root":    self.project_root,
            "poll_interval_s": self.poll_interval,
            "debounce_s":      self.debounce,
            "scan_count":      self.scan_count,
            "last_check":      _fmt(self.last_check_at),
            "last_scan":       _fmt(self.last_scan_at),
            "last_scan_files": self.last_scan_files,
        }
