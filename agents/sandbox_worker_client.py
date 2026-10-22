
"""Client for submitting Python jobs to the isolated Docker sandbox worker."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from contracts import CodeExecutionResult

JOBS_ROOT = Path(os.getenv("SANDBOX_JOBS_DIR", "/jobs"))
JOBS_IN = JOBS_ROOT / "in"
JOBS_OUT = JOBS_ROOT / "out"

MAX_CAPTURED_CHARS = 4000


def run_python_via_worker(
    code: str,
    timeout_seconds: float = 8,
    memory_mb: int = 256,
) -> CodeExecutionResult:
    """Run Python code through the separate Docker sandbox worker."""

    del memory_mb  # The worker container enforces its own resource limits.

    start = time.monotonic()
    job_id = uuid.uuid4().hex

    input_file = JOBS_IN / f"{job_id}.py"
    temp_input = JOBS_IN / f".{job_id}.tmp"
    output_file = JOBS_OUT / f"{job_id}.json"

    try:
        if not JOBS_IN.is_dir() or not JOBS_OUT.is_dir():
            raise RuntimeError(
                f"Sandbox job directories are unavailable: {JOBS_ROOT}"
            )

        # Atomically publish the input so the worker sees a complete file.
        temp_input.write_text(code, encoding="utf-8")
        temp_input.replace(input_file)

        # The worker's own execution limit is 8 seconds by default.
        # Allow additional time for polling and result delivery.
        deadline = start + max(timeout_seconds, 0.1) + 4

        while time.monotonic() < deadline:
            if output_file.is_file():
                result = json.loads(
                    output_file.read_text(encoding="utf-8")
                )

                if result.get("job_id") != job_id:
                    raise RuntimeError(
                        "Sandbox returned a mismatched job ID"
                    )

                return CodeExecutionResult(
                    stdout=str(result.get("stdout", ""))[
                        :MAX_CAPTURED_CHARS
                    ],
                    stderr=str(result.get("stderr", ""))[
                        :MAX_CAPTURED_CHARS
                    ],
                    exit_code=int(result.get("exit_code", -1)),
                    timed_out=bool(result.get("timed_out", False)),
                    duration_seconds=round(
                        float(result.get("duration_seconds", 0)), 3
                    ),
                )

            time.sleep(0.1)

        return CodeExecutionResult(
            stdout="",
            stderr=(
                "Docker sandbox worker did not return a result "
                "before the deadline."
            ),
            exit_code=-1,
            timed_out=True,
            duration_seconds=round(time.monotonic() - start, 3),
        )

    except Exception as exc:
        return CodeExecutionResult(
            stdout="",
            stderr=f"Docker sandbox worker error: {exc}"[
                :MAX_CAPTURED_CHARS
            ],
            exit_code=-1,
            timed_out=False,
            duration_seconds=round(time.monotonic() - start, 3),
        )

    finally:
        # Clean up only files belonging to this request.
        input_file.unlink(missing_ok=True)
        temp_input.unlink(missing_ok=True)
        output_file.unlink(missing_ok=True)
