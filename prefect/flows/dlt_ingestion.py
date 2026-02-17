import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"))

import dlt
import random
from prefect import task
from datetime import datetime, timedelta


@dlt.resource(name="orders")
def generate_orders():
    """Generate sample order data"""
    categories = ['Electronics', 'Clothing', 'Food', 'Books']
    cities = ['New York', 'Los Angeles', 'Chicago', 'Houston']
    
    orders = []
    for i in range(100):
        order = {
            'order_id': i + 1000,
            'customer_id': random.randint(1, 50),
            'order_date': (datetime.now() - timedelta(days=random.randint(0, 30))).date().isoformat(),
            'category': random.choice(categories),
            'city': random.choice(cities),
            'amount': round(random.uniform(10, 500), 2),
            'quantity': random.randint(1, 5)
        }
        orders.append(order)
    
    yield orders

@dlt.resource(name="customers")
def generate_customers():
    """Generate sample customer data"""
    customers = []
    for i in range(1, 51):
        customer = {
            'customer_id': i,
            'name': f'Customer_{i}',
            'email': f'customer{i}@example.com',
            'city': random.choice(['New York', 'Los Angeles', 'Chicago', 'Houston']),
            'signup_date': (datetime.now() - timedelta(days=random.randint(0, 365))).date().isoformat()
        }
        customers.append(customer)
    
    yield customers

@task(retries=2, retry_delay_seconds=30)
def run_dlt_pipeline():
    base_dir = "/Users/agha.syaifullah/Documents/data-platform-data"

    pipeline = dlt.pipeline(
        pipeline_name='analytics',
        dataset_name='raw',
        destination=dlt.destinations.duckdb(
            credentials=os.environ["ANALYTICS_DB_PATH"]
        ),
        pipelines_dir=os.environ["ANALYTICS_PIPELINES_DIR"]
    )
    load_info = pipeline.run([generate_orders(), generate_customers()])
    
    print(f"pipelines_dir: {pipeline.pipelines_dir}")
    print(f"working_dir: {pipeline.working_dir}")
    print(f"initial_cwd: {pipeline.initial_cwd}")
    print(f"config: {pipeline.config}")

    print(f"Load complete: {load_info}")
    return load_info

if __name__ == "__main__":
    run_dlt_pipeline()