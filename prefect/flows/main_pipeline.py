import path_setup
from prefect import flow
from dlt_ingestion import run_dlt
from dbt_transformation import run_dbt
from evidence_build import build_evidence

@flow(name="analytics_pipeline")
def analytics_pipeline():
    run_dlt()
    run_dbt()
    build_evidence()

if __name__ == "__main__":
    analytics_pipeline()