import json
import requests
from config import SUPERSET_BASE_URL, SUPERSET_USERNAME, SUPERSET_PASSWORD


def get_session():
    session = requests.Session()

    r = session.post(f"{SUPERSET_BASE_URL}/api/v1/security/login", json={
        "username": SUPERSET_USERNAME,
        "password": SUPERSET_PASSWORD,
        "provider": "db",
        "refresh": True,
    })
    r.raise_for_status()
    access_token = r.json()["access_token"]

    r2 = session.get(
        f"{SUPERSET_BASE_URL}/api/v1/security/csrf_token/",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    r2.raise_for_status()
    csrf_token = r2.json()["result"]

    session.headers.update({
        "Authorization": f"Bearer {access_token}",
        "X-CSRFToken": csrf_token,
        "Content-Type": "application/json",
        "Referer": SUPERSET_BASE_URL,
    })

    return session


def get_database_id(session: requests.Session, db_name: str = "DuckDB") -> int:
    r = session.get(f"{SUPERSET_BASE_URL}/api/v1/database/")
    r.raise_for_status()
    for db in r.json()["result"]:
        if db_name.lower() in db["database_name"].lower():
            return db["id"]
    raise ValueError(f"No database found matching '{db_name}'")


def get_or_create_dataset(session: requests.Session, table_name: str, schema: str, database_id: int, sql: str = None) -> int:
    body = {
        "database": database_id,
        "schema": schema,
        "table_name": table_name,
    }
    if sql:
        body["sql"] = sql

    r = session.post(f"{SUPERSET_BASE_URL}/api/v1/dataset/", json=body)

    if r.status_code == 422:
        r2 = session.get(f"{SUPERSET_BASE_URL}/api/v1/dataset/")
        r2.raise_for_status()
        for ds in r2.json().get("result", []):
            if ds["table_name"] == table_name and ds.get("schema") == schema:
                dataset_id = ds["id"]
                # Update existing dataset with new SQL
                if sql:
                    session.put(
                        f"{SUPERSET_BASE_URL}/api/v1/dataset/{dataset_id}",
                        json={"sql": sql}
                    )
                break
        else:
            raise ValueError(f"Dataset {schema}.{table_name} exists but could not be found")
    else:
        r.raise_for_status()
        dataset_id = r.json()["id"]

    # Refresh dataset columns so Superset knows the schema of the SQL result
    session.put(f"{SUPERSET_BASE_URL}/api/v1/dataset/{dataset_id}/refresh")

    return dataset_id


def create_chart(session: requests.Session, title: str, dataset_id: int) -> int:
    # Fetch refreshed columns
    r = session.get(f"{SUPERSET_BASE_URL}/api/v1/dataset/{dataset_id}")
    r.raise_for_status()
    columns = r.json()["result"]["columns"]
    col_names = [col["column_name"] for col in columns]

    params = json.dumps({
        "adhoc_filters": [],
        "all_columns": col_names,
        "query_mode": "raw",
        "row_limit": 1000,
        "order_desc": False,
    })

    r = session.post(f"{SUPERSET_BASE_URL}/api/v1/chart/", json={
        "slice_name": title,
        "viz_type": "table",
        "datasource_id": dataset_id,
        "datasource_type": "table",
        "params": params,
        "query_context": "",
    })
    r.raise_for_status()
    return r.json()["id"]


def build_position_json(chart_ids: list[int], chart_names: list[str] = None) -> str:
    positions = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"children": ["GRID_ID"], "id": "ROOT_ID", "type": "ROOT"},
        "GRID_ID": {"children": [], "id": "GRID_ID", "type": "GRID"},
    }

    for i, chart_id in enumerate(chart_ids):
        row_id = f"ROW-{i}"
        chart_key = f"CHART-{chart_id}"

        positions["GRID_ID"]["children"].append(row_id)
        positions[row_id] = {
            "children": [chart_key],
            "id": row_id,
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
            "type": "ROW",
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
            "type": "CHART",
        }

    return json.dumps(positions)


def create_dashboard(session: requests.Session, title: str, chart_ids: list[int], chart_names: list[str] = None) -> dict:
    position_json = build_position_json(chart_ids, chart_names)

    r = session.post(f"{SUPERSET_BASE_URL}/api/v1/dashboard/", json={
        "dashboard_title": title,
        "published": True,
        "position_json": position_json,
        "slug": None,
    })
    r.raise_for_status()
    dashboard_id = r.json()["id"]

    # Link charts to dashboard via chart endpoint (proven pattern from test_superset.py)
    for chart_id in chart_ids:
        session.put(
            f"{SUPERSET_BASE_URL}/api/v1/chart/{chart_id}",
            json={"dashboards": [dashboard_id]}
        )

    return {
        "dashboard_id": dashboard_id,
        "url": f"{SUPERSET_BASE_URL}/superset/dashboard/{dashboard_id}/",
    }