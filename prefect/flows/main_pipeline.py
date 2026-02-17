from prefect import flow
from flows.dlt_ingestion import run_dlt_pipeline
from flows.dbt_transformation import run_dbt

@flow(name="analytics_pipeline")
def analytics_pipeline():
    run_dlt_pipeline()
    run_dbt()

if __name__ == "__main__":
    # For local testing without deployment
    analytics_pipeline.serve()