"""
RainWise : Daily Rainfall Ingestion DAG
--------------------------------------

Pulls current-hour rainfall data for a single city from the OpenWeatherMap
“Current Weather Data” endpoint and stores a JSON record in the raw-data
landing zone.  Meant as the first (E = Extract) step of the end-to-end
RainWise pipeline.

Execution schedule
    └─ Cron: At 10 :00 every day (Docker container time)

Author
    Gabriel <gmm.maire@gmail.com>
"""

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import os, requests, json, pathlib, time

# ---------------------------------------------------------------------------
# Constants & configuration
# ---------------------------------------------------------------------------
CITY = "Biarritz"
COUNTRY_CODE = "FR"
RAW_DIR = "/opt/airflow/data/raw"       # Docker volume mount path
DAG_ID = "rainfall_daily"       # Appears in Airflow UI

# ---------------------------------------------------------------------------
# Helper function – does the extraction + raw‑file write
# ---------------------------------------------------------------------------
def extract_store(**_):
    """
    Task callable – Extract a single weather snapshot and write to disk.

    Steps
    -----
    1. Build the OpenWeatherMap API URL with metric units.
    2. Perform GET request (10-second timeout, raises for non-2xx).
    3. Parse JSON, pulling `rain.1h` if present, default 0.0 mm.
    4. Assemble a concise record and write `<city>_<epoch>.json`
       into RAW_DIR (creates directory tree if missing).

    XComs
    -----
    None : we persist the file to the raw landing zone instead.
    """
    
    # Build URL
    api_key = os.environ["OWM_API_KEY"]     # Provided via Docker env‑var
    if not api_key:
        raise EnvironmentError("Environment variable OWM_API_KEY is missing")
    url = (
        "https://api.openweathermap.org/data/2.5/weather"
        f"?q={CITY},{COUNTRY_CODE}&appid={api_key}&units=metric"
    )

    # HTTP request
    response = requests.get(url, timeout=10)
    response.raise_for_status()  # Will retry via DAG on non-success
    data = response.json()

    # Extract rainfall
    rain_mm = data.get("rain", {}).get("1h", 0.0)
    out = {
        "city": CITY,
        "timestamp": data["dt"],    # Unix epoch (UTC)
        "datetime_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(data["dt"])),
        "rainfall_mm": rain_mm,
    }

    # Write to raw folder
    pathlib.Path(RAW_DIR).mkdir(parents=True, exist_ok=True)
    fname = f"{CITY.split(',')[0].lower()}_{data['dt']}.json"
    with open(pathlib.Path(RAW_DIR, fname), "w") as f:
        json.dump(out, f, indent=2)

    # Simple log for Airflow task output
    print(f"Saved {fname}", flush=True)

# ---------------------------------------------------------------------------
# DAG definition – scheduling & task graph
# ---------------------------------------------------------------------------
default_args = {
    "owner": "gabriel",
    "retries": 1,                           # one retry on transient error
    "retry_delay": timedelta(minutes=5),    # wait 5 min before retry
}

with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    start_date=datetime(2025, 5, 1),    # historical anchor
    schedule="0 10 * * *",              # daily at 10:00
    catchup=False,                      # skip backlog runs
    tags=["rainwise", "ingestion"],
) as dag:

    fetch_rainfall = PythonOperator(
        task_id="extract_and_store",
        python_callable=extract_store,
    )
    
    # In this simple DAG there is a single task; add >> downstream tasks later
    fetch_rainfall