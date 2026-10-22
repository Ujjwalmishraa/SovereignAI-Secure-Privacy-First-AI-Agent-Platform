
"""Python code execution through the isolated Docker sandbox worker."""

from __future__ import annotations

import os

from contracts import CodeExecutionResult
from agents.sandbox_worker_client import run_python_via_worker

DEFAULT_TIMEOUT_SECONDS = float(
    os.getenv("SANDBOX_TIMEOUT_SECONDS", "8")
)
DEFAULT_MEMORY_MB = int(
    os.getenv("SANDBOX_MEMORY_MB", "256")
)


def run_python(
    code: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    memory_mb: int = DEFAULT_MEMORY_MB,
) -> CodeExecutionResult:
    """Execute code in the separate, isolated Docker sandbox worker.

    The worker executes the submitted Python code and returns its actual
    stdout, stderr, exit status, timeout status, and execution duration.

    Failures are returned as unsuccessful CodeExecutionResult objects.
    No model calls or code execution happen inside the API process.
    """
    return run_python_via_worker(
        code=code,
        timeout_seconds=timeout_seconds,
        memory_mb=memory_mb,
    )
