import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("SUPERSET_BASE_URL", "http://localhost:8088")
USERNAME = os.getenv("SUPERSET_USERNAME", "admin")
PASSWORD = os.getenv("SUPERSET_PASSWORD", "admin")

# --- Auth ---

session = requests.Session()

def get_tokens():
    r = session.post(f"{BASE_URL}/api/v1/security/login", json={
        "username": USERNAME,
        "password": PASSWORD,
        "provider": "db",
        "refresh": True
    })
    r.raise_for_status()
    access_token = r.json()["access_token"]

    r2 = session.get(
        f"{BASE_URL}/api/v1/security/csrf_token/",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    r2.raise_for_status()
    csrf_token = r2.json()["result"]

    return access_token, csrf_token

def headers(access_token, csrf_token):
    return {
        "Authorization": f"Bearer {access_token}",
        "X-CSRFToken": csrf_token,
        "Content-Type": "application/json",
        "Referer": BASE_URL,
    }

# --- Step 1: Find the DuckDB database ID ---

def get_database_id(access_token, csrf_token, db_name="DuckDB"):
    r = session.get(
        f"{BASE_URL}/api/v1/database/",
        headers=headers(access_token, csrf_token)
    )
    r.raise_for_status()
    for db in r.json()["result"]:
        if db_name.lower() in db["database_name"].lower():
            print(f"Found database: {db['database_name']} (id={db['id']})")
            return db["id"]
    raise ValueError(f"No database found matching '{db_name}'")

# --- Step 2: Create a dataset ---

def create_dataset(access_token, csrf_token, database_id, table_name, schema=None):
    payload = {
        "database": database_id,
        "table_name": table_name,
        "schema": schema or "",
    }
    r = session.post(
        f"{BASE_URL}/api/v1/dataset/",
        headers=headers(access_token, csrf_token),
        json=payload
    )
    if r.status_code == 422:
        print(f"Dataset already exists, fetching existing...")
        r2 = session.get(
            f"{BASE_URL}/api/v1/dataset/",
            headers=headers(access_token, csrf_token)
        )
        r2.raise_for_status()
        for ds in r2.json().get("result", []):
            if ds["table_name"] == table_name and ds.get("schema") == schema:
                print(f"Reusing existing dataset id={ds['id']}")
                return ds["id"]
        raise ValueError(f"Dataset {schema}.{table_name} exists but could not be found via GET")
    if not r.ok:
        print("Error response:", r.json())
        r.raise_for_status()
    dataset_id = r.json()["id"]
    print(f"Created dataset id={dataset_id}")
    return dataset_id

# --- Step 3: Create a chart ---

def create_chart(access_token, csrf_token, dataset_id, chart_name):
    payload = {
        "datasource_id": dataset_id,
        "datasource_type": "table",
        "slice_name": chart_name,
        "viz_type": "echarts_timeseries_bar",
        "params": json.dumps({
            "adhoc_filters": [],
            "metrics": [
                {
                    "aggregate": "SUM",
                    "column": {
                        "column_name": "amount",
                        "type": "DOUBLE",
                    },
                    "expressionType": "SIMPLE",
                    "label": "SUM(amount)",
                }
            ],
            "order_desc": True,
            "row_limit": 100,
            "x_axis": "category",
        }),
    }
    r = session.post(
        f"{BASE_URL}/api/v1/chart/",
        headers=headers(access_token, csrf_token),
        json=payload
    )
    if not r.ok:
        print("Chart error:", r.json())
        r.raise_for_status()
    chart_id = r.json()["id"]
    print(f"Created chart id={chart_id}")
    return chart_id

# --- Step 4: Create a dashboard with position_json ---
def build_position_json(chart_ids, chart_names=None):
    """
    Builds a simple grid layout for a list of chart IDs.
    Each chart gets a row of its own, full width (12 cols).
    Uses the same structure Superset exports — do not generate from scratch,
    this mirrors the exported template pattern.
    """
    positions = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {
            "children": ["GRID_ID"],
            "id": "ROOT_ID",
            "type": "ROOT"
        },
        "GRID_ID": {
            "children": [],
            "id": "GRID_ID",
            "type": "GRID"
        },
    }

    for i, chart_id in enumerate(chart_ids):
        row_id = f"ROW-{i}"
        chart_key = f"CHART-{chart_id}"

        positions["GRID_ID"]["children"].append(row_id)

        positions[row_id] = {
            "children": [chart_key],
            "id": row_id,
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
            "type": "ROW"
        }
        positions[chart_key] = {
            "children": [],
            "id": chart_key,
            "meta": {
                "chartId": chart_id,
                "height": 50,
                "sliceName": chart_names[i] if chart_names else f"Chart {chart_id}",
                "width": 12,
            },
            "type": "CHART"
        }

    return json.dumps(positions)

def create_dashboard(access_token, csrf_token, dashboard_title, chart_ids, chart_names=None):
    position_json = build_position_json(chart_ids, chart_names)
    payload = {
        "dashboard_title": dashboard_title,
        "published": True,
        "position_json": position_json,
        "slug": None,
    }
    r = session.post(
        f"{BASE_URL}/api/v1/dashboard/",
        headers=headers(access_token, csrf_token),
        json=payload
    )
    r.raise_for_status()
    dashboard_id = r.json()["id"]
    print(f"Created dashboard id={dashboard_id}")
    return dashboard_id

# def add_chart_to_dashboard(access_token, csrf_token, dashboard_id, chart_ids):
#     """Explicitly link charts to dashboard (required in some Superset versions)."""
#     r = session.put(
#         f"{BASE_URL}/api/v1/dashboard/{dashboard_id}",
#         headers=headers(access_token, csrf_token),
#         json={"charts": chart_ids}
#     )
#     # 404/422 here is non-fatal — position_json already embeds the chart reference
#     if r.status_code not in (200, 201, 400, 404, 422):
#         r.raise_for_status()
#     print(f"Linked charts {chart_ids} to dashboard {dashboard_id}")

def link_charts_to_dashboard(access_token, csrf_token, dashboard_id, chart_ids):
    for chart_id in chart_ids:
        r = session.put(
            f"{BASE_URL}/api/v1/chart/{chart_id}",
            headers=headers(access_token, csrf_token),
            json={"dashboards": [dashboard_id]}
        )
        print(f"Chart {chart_id} link status: {r.status_code} — {r.json()}")


# --- Main ---

if __name__ == "__main__":
    print("Authenticating...")
    access_token, csrf_token = get_tokens()

    print("\nFinding DuckDB connection...")
    db_id = get_database_id(access_token, csrf_token)

    # ⚠️ Replace with an actual table name from your analytics.duckdb
    TABLE_NAME = "orders"   # <-- change this

    print(f"\nCreating dataset for table '{TABLE_NAME}'...")
    dataset_id = dataset_id = create_dataset(access_token, csrf_token, db_id, TABLE_NAME, schema="raw")

    print("\nCreating chart...")
    chart_id = create_chart(access_token, csrf_token, dataset_id, f"API Test — {TABLE_NAME} Table")
    print(f"\nChart ID to embed: {chart_id}")
    
    print("\nCreating dashboard...")
    dashboard_id = create_dashboard(
        access_token, 
        csrf_token,
        dashboard_title="API Test Dashboard",
        chart_ids=[chart_id],
        chart_names=[f"API Test — {TABLE_NAME} Table"]
    )

    link_charts_to_dashboard(access_token, csrf_token, dashboard_id, [chart_id])

    print(f"\n✅ Done! View at: {BASE_URL}/superset/dashboard/{dashboard_id}/")