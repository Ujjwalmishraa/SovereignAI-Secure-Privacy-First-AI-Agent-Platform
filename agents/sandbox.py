"""Deterministic, isolated Python code execution sandbox.

NON-NEGOTIABLE DESIGN PRINCIPLES (same discipline as harness/verify.py):
1. Zero model calls in this module. This is pure Python + OS process
   isolation. The model proposes code; THIS module disposes of it by
   actually running it and reporting exactly what happened.
2. Runs in a fresh subprocess, never in-process -- a model-proposed script
   must never be able to import or touch anything in the SEVERANCE server
   process (contracts, trust, auth, the SQLite ledger, etc).
3. Hard resource limits: wall-clock timeout, memory cap (POSIX via
   `resource`, best-effort no-op on platforms without it), and no network
   access from the child (best-effort via a stripped/marked environment --
   true network isolation is provided at the container/orchestration layer,
   see docker-compose.yml's `sandbox` service and ops/network_monitor.py).
4. Never trust the child process's own claims -- stdout/stderr/exit_code are
   read directly from the OS pipe/exit status, not parsed from the code's
   self-reported output.
5. Fails closed: any exception while attempting to sandbox execution is
   reported as a failed CodeExecutionResult, never silently swallowed into
   a false "success".
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

from contracts import CodeExecutionResult

DEFAULT_TIMEOUT_SECONDS = float(os.getenv("SANDBOX_TIMEOUT_SECONDS", "8"))
DEFAULT_MEMORY_MB = int(os.getenv("SANDBOX_MEMORY_MB", "256"))
MAX_CAPTURED_CHARS = 4000


def _limit_resources(memory_mb: int) -> "callable[[], None]":
    """Return a preexec_fn that caps child memory and disables core dumps.

    POSIX-only (Linux/macOS). On platforms without the `resource` module
    (e.g. native Windows), returns a no-op -- the wall-clock timeout below
    is still enforced regardless of platform.
    """
    try:
        import resource
    except ImportError:
        return lambda: None

    mem_bytes = memory_mb * 1024 * 1024

    def _apply() -> None:
        try:
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        except (ValueError, OSError):
            pass
        try:
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        except (ValueError, OSError):
            pass

    return _apply


def run_python(
    code: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    memory_mb: int = DEFAULT_MEMORY_MB,
) -> CodeExecutionResult:
    """Execute `code` as a standalone Python script in an isolated subprocess.

    Returns a CodeExecutionResult carrying the REAL outcome -- stdout,
    stderr, exit code, and whether it was killed for exceeding the time
    limit. Never raises: any failure to even launch the subprocess is
    reported as exit_code=-1 with the error text in stderr, so callers
    (harness/code_runner.py) can treat it uniformly as a failed attempt
    and retry or abstain, exactly like a failed citation verification.
    """
    start = time.monotonic()

    try:
        with tempfile.TemporaryDirectory(prefix="severance_sandbox_") as tmpdir:
            script_path = Path(tmpdir) / "snippet.py"
            script_path.write_text(code, encoding="utf-8")

            preexec = _limit_resources(memory_mb) if sys.platform != "win32" else None

            try:
                proc = subprocess.run(
                    [sys.executable, "-I", "-S", str(script_path)],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    preexec_fn=preexec,
                    env={"PATH": "/usr/bin:/bin"},  # stripped env: no inherited secrets/config
                )
                duration = time.monotonic() - start
                return CodeExecutionResult(
                    stdout=proc.stdout[:MAX_CAPTURED_CHARS],
                    stderr=proc.stderr[:MAX_CAPTURED_CHARS],
                    exit_code=proc.returncode,
                    timed_out=False,
                    duration_seconds=round(duration, 3),
                )
            except subprocess.TimeoutExpired as exc:
                duration = time.monotonic() - start
                return CodeExecutionResult(
                    stdout=(exc.stdout or "")[:MAX_CAPTURED_CHARS] if isinstance(exc.stdout, str) else "",
                    stderr=f"Execution exceeded the {timeout_seconds}s sandbox time limit and was terminated.",
                    exit_code=-1,
                    timed_out=True,
                    duration_seconds=round(duration, 3),
                )
    except Exception as exc:  # noqa: BLE001 - fail closed, never let a sandbox bug look like success
        duration = time.monotonic() - start
        return CodeExecutionResult(
            stdout="",
            stderr=f"Sandbox failed to execute code: {exc}",
            exit_code=-1,
            timed_out=False,
            duration_seconds=round(duration, 3),
        )
