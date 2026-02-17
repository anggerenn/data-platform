from prefect import task
import subprocess
import os

@task(retries=2, retry_delay_seconds=30)
def run_dbt():
    """Run dbt transformations"""
    result = subprocess.run(["dbt", "run"], cwd="/opt/prefect/dbt", capture_output=True, text=True, check=True)
    print(result.stdout)
    return True