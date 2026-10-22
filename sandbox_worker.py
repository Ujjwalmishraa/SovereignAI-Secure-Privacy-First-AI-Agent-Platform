import json
import time
from pathlib import Path

from sandbox import run_python

JOBS_IN = Path("/jobs/in")
JOBS_OUT = Path("/jobs/out")

JOBS_IN.mkdir(parents=True, exist_ok=True)
JOBS_OUT.mkdir(parents=True, exist_ok=True)


def process_job(job_file: Path) -> None:
    job_id = job_file.stem

    try:
        code = job_file.read_text(encoding="utf-8")

        result = run_python(code)

        output = {
            "job_id": job_id,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "duration_seconds": result.duration_seconds,
        }

        temp_file = JOBS_OUT / f"{job_id}.tmp"
        result_file = JOBS_OUT / f"{job_id}.json"

        temp_file.write_text(
            json.dumps(output),
            encoding="utf-8"
        )

        temp_file.replace(result_file)

    except Exception as exc:
        output = {
            "job_id": job_id,
            "stdout": "",
            "stderr": f"Sandbox worker error: {exc}",
            "exit_code": -1,
            "timed_out": False,
            "duration_seconds": 0,
        }

        result_file = JOBS_OUT / f"{job_id}.json"
        result_file.write_text(
            json.dumps(output),
            encoding="utf-8"
        )

    finally:
        job_file.unlink(missing_ok=True)


print("Sandbox worker started.")

while True:
    for job in sorted(JOBS_IN.glob("*.py")):
        process_job(job)

    time.sleep(0.5)
