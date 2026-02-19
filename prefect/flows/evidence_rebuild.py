import subprocess
from prefect import task, flow

@task(retries=1, retry_delay_seconds=10)
def rebuild_evidence():
    result = subprocess.run(
        ["npm", "run", "sources", "&&", "npm", "run", "build"],
        cwd="/data/evidence",
        shell=True,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise Exception(f"Evidence build failed:\n{result.stderr}")
    return "Evidence rebuilt successfully"