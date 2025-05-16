"""
RainWise : Daily Rainfall ETL DAG
---------------------------------

Pulls current-hour rainfall data for one city from the OpenWeatherMap
“Current Weather Data” endpoint, lands a JSON record in the raw zone,
and immediately inserts the same data into the PostgreSQL `rainfall`
table (creating the table automatically if it does not exist).

Task graph
    ┌─ create_table (PostgresOperator)
    │
    └─ extract_openweather (PythonOperator)
         ↓  XCom dict {city, record_ts, rainfall_mm}
       load_into_pg (PythonOperator)

Execution schedule
    └─ Every 10 mins.

Author
    Gabriel <gmm.maire@gmail.com>
"""

# ---------------------------------------------------------------------------#
# Imports                                                                    #
# ---------------------------------------------------------------------------#
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from great_expectations_provider.operators.great_expectations import GreatExpectationsOperator
from datetime import datetime, timedelta, timezone
import os, requests, json, pathlib, time, psycopg2

# ---------------------------------------------------------------------------#
# Constants & configuration                                                  #
# ---------------------------------------------------------------------------#
CITY = "Biarritz"
COUNTRY_CODE = "FR"
RAW_DIR = "/opt/airflow/data/raw"             # Docker-volume mount path
PG_CONN_ID = "postgres_rainwise"              # set in docker-compose cmd
SQL_TABLE_PATH = "sql/create_rainfall_table.sql"
CREATE_MV_SQL_PATH = "sql/create_mv_rainfall_hourly.sql"
DAG_ID = "rainfall_daily"

# ---------------------------------------------------------------------------#
# Task helpers                                                               #
# ---------------------------------------------------------------------------#
def extract_openweather(**context):
    """
    Extract a single weather snapshot and push a cleaned dict to XCom.
    Also writes a copy of the raw record to the landing zone for auditing.
    """
    api_key = os.environ.get("OWM_API_KEY")
    if not api_key:
        raise EnvironmentError("OWM_API_KEY not set in the container env")

    # Build API URL
    url = (
        "https://api.openweathermap.org/data/2.5/weather"
        f"?q={CITY},{COUNTRY_CODE}&appid={api_key}&units=metric"
    )

    # GET request (10-s timeout)
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    # Extract rainfall
    rain_mm = round(data.get("rain", {}).get("1h", 0.0), 2)

    payload = {
        "city": f"{CITY},{COUNTRY_CODE}",
        "record_ts": datetime.fromtimestamp(data["dt"], tz=timezone.utc),  # aware dt
        "rainfall_mm": rain_mm,
    }

    # Write to raw folder
    pathlib.Path(RAW_DIR).mkdir(parents=True, exist_ok=True)
    fname = f"{CITY.lower()}_{data['dt']}.json"
    with open(pathlib.Path(RAW_DIR, fname), "w") as fp:
        json.dump(payload, fp, indent=2, default=str)

    # Simple log for Airflow task output
    print(f"[extract] saved raw file → {fname}", flush=True)

    # Push to XCom for the next task
    context["ti"].xcom_push(key="rain_row", value=payload)


def load_into_pg(**context):
    """
    Pull the dict from XCom and insert it into public.rainfall.
    Uses ON CONFLICT DO NOTHING to avoid duplicate rows if DAG is retried.
    """
    row = context["ti"].xcom_pull(key="rain_row", task_ids="extract_openweather")
    if not row:
        raise ValueError("No XCom payload received from extract task")

    conn = psycopg2.connect(
        dbname="rainwise", user="airflow", password="airflow", host="postgres"
    )
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.rainfall (city, record_ts, rainfall_mm)
                VALUES (%(city)s, %(record_ts)s, %(rainfall_mm)s)
                ON CONFLICT DO NOTHING;
                """,
                row,
            )
    conn.close()
    print(f"Inserted rainfall row for {row['city']} @ {row['record_ts']}")
    #print("[load] inserted row into public.rainfall", flush=True)


# ---------------------------------------------------------------------------#
# DAG definition                                                             #
# ---------------------------------------------------------------------------#
default_args = {
    "owner": "gabriel",
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
}

with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    start_date=datetime(2025, 5, 1),
    schedule="*/10 * * * *",      # every 10 mins
    catchup=False,
    tags=["rainwise", "ingestion"],
) as dag:

    # 1. Ensure destination table exists (id column is IDENTITY, not SERIAL)
    create_table = PostgresOperator(
        task_id="create_table",
        postgres_conn_id=PG_CONN_ID,
        sql=SQL_TABLE_PATH,
    )

    # 2. Create a refined materialized view for faster querying
    create_mv = PostgresOperator(
        task_id="create_mv_hourly",
        postgres_conn_id=PG_CONN_ID,
        sql=CREATE_MV_SQL_PATH,
    )

    # 3. Extract from API & land raw JSON
    extract_task = PythonOperator(
        task_id="extract_openweather",
        python_callable=extract_openweather,
    )

    # 4. Load into PostgreSQL
    load_task = PythonOperator(
        task_id="load_into_pg",
        python_callable=load_into_pg,
    )

    # 5. Validate with GreatExpectation
    validate_task = GreatExpectationsOperator(
        task_id="validate_rainfall",
        data_context_root_dir="/opt/airflow/great_expectations",
        checkpoint_name="rainfall_checkpoint",
        fail_task_on_validation_failure=True,   # pipeline fails if tests fail
        return_json_dict=True,
    )

    # 6. Refresh the materialized view
    refresh_mv = PostgresOperator(
        task_id="refresh_mv_hourly",
        postgres_conn_id=PG_CONN_ID,
        sql="REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_rainfall_hourly;",
    )


    # Task dependencies
    create_table >> create_mv >> extract_task >> load_task >> validate_task >> refresh_mv