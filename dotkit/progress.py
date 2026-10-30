"""A live status line for slow steps: spinner, elapsed time, a bar when the fraction
is known, and the latest output line. Drawn on stderr only when it is a terminal.

    with Progress() as p:
        p.update(0.4, "Unpacking cuda-nvcc-13-4")
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
import time

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
DELAY = 1.0  # seconds before anything is drawn, so quick steps don't flicker
INDENT = "      "


def enabled() -> bool:
    from . import system  # late: system imports this module

    return sys.stderr.isatty() and not system.verbose and os.environ.get("TERM") != "dumb"


class Progress:
    def __init__(self) -> None:
        self.fraction: float | None = None
        self.text = ""
        self._start = time.monotonic()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._drawn = False

    def __enter__(self) -> Progress:
        if enabled():
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
        if self._drawn:
            sys.stderr.write("\r\033[K")
            sys.stderr.flush()

    def update(self, fraction: float | None = None, text: str | None = None) -> None:
        if fraction is not None:
            self.fraction = min(max(fraction, 0.0), 1.0)
        if text:
            self.text = " ".join(text.split())

    def _loop(self) -> None:
        if self._stop.wait(DELAY):
            return
        frame = 0
        while not self._stop.is_set():
            sys.stderr.write("\r\033[K" + self.render(frame))
            sys.stderr.flush()
            self._drawn = True
            frame += 1
            self._stop.wait(0.1)

    def render(self, frame: int = 0, width: int | None = None) -> str:
        width = width or shutil.get_terminal_size((100, 20)).columns
        elapsed = int(time.monotonic() - self._start)
        clock = f"{elapsed // 60}m{elapsed % 60:02d}s" if elapsed >= 60 else f"{elapsed}s"
        parts = [f"{INDENT}{SPINNER[frame % len(SPINNER)]} {clock:>6}"]
        if self.fraction is not None:
            filled = round(self.fraction * 24)
            parts.append(f"[{'█' * filled}{'░' * (24 - filled)}] {self.fraction * 100:3.0f}%")
        line = " ".join(parts)
        if self.text:
            line += "  " + self.text
        return line[: max(width - 1, 20)]


def size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"
