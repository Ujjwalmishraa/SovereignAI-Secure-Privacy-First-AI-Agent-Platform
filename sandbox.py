import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    duration_seconds: float


def run_python(
    code: str,
    timeout: int = 8,
    memory_mb: int = 256,
) -> ExecutionResult:

    start = time.monotonic()

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        script_path = tmpdir / "script.py"

        script_path.write_text(code, encoding="utf-8")

        def limit_resources():
            try:
                import resource

                memory_bytes = memory_mb * 1024 * 1024

                resource.setrlimit(
                    resource.RLIMIT_AS,
                    (memory_bytes, memory_bytes),
                )

                resource.setrlimit(
                    resource.RLIMIT_CORE,
                    (0, 0),
                )

            except Exception:
                pass

        try:
            process = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    str(script_path),
                ],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={
                    "PATH": "/usr/bin:/bin",
                },
                preexec_fn=limit_resources,
            )

            return ExecutionResult(
                stdout=process.stdout,
                stderr=process.stderr,
                exit_code=process.returncode,
                timed_out=False,
                duration_seconds=time.monotonic() - start,
            )

        except subprocess.TimeoutExpired as exc:
            return ExecutionResult(
                stdout=exc.stdout or "",
                stderr=exc.stderr or "Execution timed out",
                exit_code=-1,
                timed_out=True,
                duration_seconds=time.monotonic() - start,
            )

        except Exception as exc:
            return ExecutionResult(
                stdout="",
                stderr=f"Sandbox execution failed: {exc}",
                exit_code=-1,
                timed_out=False,
                duration_seconds=time.monotonic() - start,
            )
