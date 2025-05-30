<!----------------------------------------------------------->
# 🌧️ RainWise – Rainfall Insights Pipeline
<!----------------------------------------------------------->

> **Goal:** Make live, daily and hourly rainfall data of multiple cities **easy to access, query and visualise** for farmers, city planners and curious citizens.  
> Pipeline: *Python → Airflow → PostgreSQL → Streamlit.*

---

## 📑 Table of Contents
1. [Project Overview](#project-overview)  
2. [Data Caveats](#data-caveats)
2. [Architecture](#architecture)  
3. [Quick Start (Local)](#quick-start-local)  
4. [Folder Structure](#folder-structure)  
5. [Tech Stack](#tech-stack)  
6. [OpenWeatherMap API Usage](#openweathermap-api-usage)  
7. [Roadmap](#roadmap)  
8. [Contributing](#contributing)  
9. [License](#license)

---

## Project Overview
RainWise is an end-to-end **data engineering demo**:

* **Ingestion** – pulls hourly weather records from OpenWeatherMap.  
* **Storage** – lands raw JSON ➜ cleans ➜ loads into PostgreSQL.  
* **Orchestration** – Apache Airflow schedules & monitors the ETL.  
* **Data Quality** – Great Expectations validates freshness and ranges.  
* **Analytics** – Streamlit dashboard exposes ad-hoc queries & CSV export.

---

## Data Caveats
RainWise uses the `rain.1h` field from OpenWeatherMap’s **Current Weather API**.

For this demo project, we consider that `rain.1h` reflects the **amount of mm of rain that fell in the past hour at the time of recording**.

However, this field is: 
* **Poorly documented.** 
* **Volatile across short intervals.**
* **Not guarenteed to reflect consistent hourly windows.**

Example: several consecutive readings at short intervals may show:
```makefile
5:00pm   →  0 mm
5:30pm   →  2.5 mm
5:45pm   →  2.0 mm
6:00pm   →  0 mm
```
Even though consequent rain fell between 5–6pm, a system that samples only at 6:00pm would falsely show 0 mm.

### Why we still use it

RainWise is a **demo data pipeline**, designed to showcase:

* ETL orchestration (Airflow)
* Data quality checks (Great Expectations)
* Reporting dashboards (Streamlit)
* GitHub CI integration

The system still adds value as a template — and as a learning project. But if built for real decision-making (e.g. agriculture or infrastructure), we’d replace the source with:

* A rainfall sensor (IoT / MQTT)
* National weather services (NOAA, Météo France)
* OpenMeteo or Meteomatics (more rigorous APIs)

---

## Architecture

```mermaid
flowchart TD
    subgraph ETL Pipeline
        A1[Extract 🌐 Current Weather API] --> A2[Raw JSON Insert into rainfall: bronze layer]
        A2 --> A3[Validate with GX ✅]
        A3 --> A4[Materialize to mv_rainfall_hourly: silver layer]
        A4 --> A5[Refresh MV ⏳ after every load]
    end

    subgraph Orchestration
        DAG[Airflow DAG] --> A1
        DAG --> A3
        DAG --> A4
        DAG --> A5
    end

    A5 --> DB[(PostgreSQL)]

    subgraph Serving Layer
        S[📊 Streamlit Dashboard]
    end

    subgraph CI/CD
        GHA[GitHub Actions] --> GXCI[Run GX checkpoint ✅]
    end

    GHA --> DB
    DAG --> DB
    S --> DB
```

**🧊 ETL Pipeline (10-minute interval)**  
- `extract_openweather()` calls OpenWeatherMap API  
- Raw JSON inserted into `public.rainfall` table: **bronze layer**
- GX checkpoint validates range, non-null  
- Postgres MV (`mv_rainfall_hourly`) deduplicates to 1 row/hour: **silver layer**
- MV refreshed in Airflow after each load step  

**⚙️ Orchestration**  
- Apache Airflow (LocalExecutor)  
- DAG: `create_table` → `create_materialized_view` → `extract_openweather` → `load_into_pg` → `validate_rainfall` → `refresh_mv_hourly` 

**🐳 Containers (via docker-compose)**  
- `airflow-webserver`, `airflow-scheduler`, `postgres`, `streamlit`  
- `.env` file controls secrets and API keys  
- All services built from one command: `docker compose up --build`  

**📊 Serving layer**  
- Streamlit app queries both `public.rainfall` (live) and `mv_rainfall_hourly` (historical)  
- Users can explore:  
    1. Live rainfall (mm/h in the last hour)  
    2. Daily totals (between dates)  
    3. Hourly breakdown (per day)  
    4. Dry vs wet ratio  

**🔄 Continuous Integration (CI)**
- GitHub Actions workflow:
  - ✅ Installs Python deps
  - ✅ Spins up Postgres service
  - ✅ Applies table creation SQL
  - ✅ Runs Great Expectations checkpoint `rainfall_checkpoint`
- If GX fails, the build fails

---

## Quick Start (Local)

> **Prerequisites:** Python 3.11, Git, Docker Desktop (WSL 2 backend on Windows).

```bash
# 1 Clone repo
$ git clone https://github.com/Lystme/rainwise.git && cd rainwise

# 2 Create secrets from template
$ cp .env.example .env  # then edit three lines with real keys

# 3 Boot entire stack (first run ≈ 2 min build)
$ docker compose up --build

# 4 Open in browser
#    • Airflow   → http://localhost:8080   (admin / admin)
#    • Streamlit → http://localhost:8501   (live dashboard)

# Stop
Ctrl‑C + docker compose down
```
> Airflow and Streamlit containers read secrets directly from .env.

`List of Cities` available in the `dags/rainfall_etl.py` file. Modify the list as you wish. **Safe up to 200 cities** without touching the Free-tier monthly API calls quota (1 000 000 calls)

---

## Folder Structure

```bash
rainwise/
├─ .github/workflows/ci.yml     # CI: lint + GX checkpoint on each push
├─ dags/                        # Airflow DAG + SQL helpers
│   └─ sql/
├─ great_expectations/          # GX data‑context
├─ streamlit_app/app.py         # Dashboard UI
├─ docker/                      # Dockerfile for Airflow & Streamlit
├─ requirements.txt             # shared Python deps
├─ docker-compose.yml           # 3‑service stack
└─ README.md
```

---

## Tech Stack

* **Python 3.13** – requests, pandas
* **Apache Airflow** – orchestration
* **PostgreSQL 16** – relational store
* **Great Expectations** – data-quality tests
* **Streamlit** – zero-friction front-end
* **Docker & docker-compose** – reproducible env
* **GitHub Actions** – CI/CD

---

## OpenWeatherMap API Notes


| Plan | Endpoints | Free-tier limits |
|------|----------------|------------------|
| **Free** | Current Weather, Geocoding, 3 h × 5 day Forecast, Weather Maps, Air Pollution | 60 calls / min &nbsp;•&nbsp; 1 000 000 calls / month |

**Endpoints in scope**
- `/data/2.5/weather` – *Current Weather API*  
- `/geo/1.0/direct` – *Geocoding* (city ⇒ lat/long)  
- `/data/2.5/forecast` – *3-hour forecast for 5 days*  
- `/tile/rain_new/{z}/{x}/{y}.png` – *Weather Maps* (optional)  
- `/data/2.5/air_pollution` – *Air Pollution*

Typical call:
```bash
GET /data/2.5/weather?q={CITY},{COUNTRY}&units=metric&appid={OWM_API_KEY}
```

---

## RoadMap

- [x] **Milestone 0** – single-city extractor script *(completed)*
- [x] **Milestone 1** – Dockerised Airflow stack with scheduled ETL DAG *(completed)*
- [x] **Milestone 2** – PostgreSQL load layer + Great Expectations data-quality suite *(completed)*
- [x] **Milestone 3** – Streamlit dashboard with filters and CSV export *(completed)*
- [x] **Milestone 4** – CI/CD via GitHub Actions (using Great Expectations checkpoint) *(completed)*
- [ ] **Milestone 5** – Optional AWS migration (S3 for raw zone, RDS for DB, MWAA for Airflow)

---

## Contributing

PRs and issues welcome! Please open an issue before large changes.

