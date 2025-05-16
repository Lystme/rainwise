"""
RainWise : Interactive Rainfall Dashboard
-----------------------------------------

Live & historical rainfall insights powered by:

    • raw 10-minute readings          : public.rainfall      (bronze)
    • hourly-dedup materialized view  : mv_rainfall_hourly   (silver)

The app offers four lenses:

    1.  Live rainfall  (last reading, mm in past hour)
    2.  Daily rainfall between dates (sum of hourly values)
    3.  Hourly rainfall for a chosen day
    4.  Dry vs Wet days between dates

Author
    Gabriel <gmm.maire@gmail.com>
"""

# ---------------------------------------------------------------------------#
# Imports                                                                    #
# ---------------------------------------------------------------------------#
from datetime import date, datetime, timedelta
import pandas as pd
import sqlalchemy as sa
import streamlit as st
import altair as alt
import os

# ---------------------------------------------------------------------------#
# Configuration                                                              #
# ---------------------------------------------------------------------------#
DB_URL = os.environ["DATABASE_URL"]
engine = sa.create_engine(DB_URL, pool_pre_ping=True)

st.set_page_config(page_title="RainWise Dashboard", layout="wide")

CACHE_TTL_LONG  = 3600   # 1 h – city list
CACHE_TTL_SHORT = 300    # 5 min – live & MV queries

# ---------------------------------------------------------------------------#
# Helper queries                                                             #
# ---------------------------------------------------------------------------#
def rows_to_df(result: sa.Result) -> pd.DataFrame:
    """Convert SQLAlchemy Result → pandas DataFrame."""
    df = pd.DataFrame(result.fetchall(), columns=result.keys())
    return df


@st.cache_data(ttl=CACHE_TTL_LONG)
def get_cities() -> list[str]:
    q = sa.text("SELECT DISTINCT city FROM public.rainfall ORDER BY city")
    with engine.begin() as conn:
        return [r[0] for r in conn.execute(q)]


@st.cache_data(ttl=CACHE_TTL_SHORT)
def get_live_rain(city: str) -> float | None:
    q = sa.text(
        "SELECT rainfall_mm FROM public.rainfall "
        "WHERE city = :city ORDER BY record_ts DESC LIMIT 1"
    )
    with engine.begin() as conn:
        row = conn.execute(q, {"city": city}).fetchone()
    return None if row is None else row[0]


@st.cache_data(ttl=CACHE_TTL_SHORT)
def fetch_daily(city: str, start: date, end: date) -> pd.DataFrame:
    q = sa.text(
        """
        SELECT date(hour_ts) AS day,
               SUM(rainfall_mm)::numeric(6,2) AS total_mm
        FROM public.mv_rainfall_hourly
        WHERE city = :city
          AND hour_ts BETWEEN :start AND :end
        GROUP BY day
        ORDER BY day
        """
    )
    with engine.begin() as conn:
        return rows_to_df(conn.execute(q, {"city": city, "start": start, "end": end}))


@st.cache_data(ttl=CACHE_TTL_SHORT)
def fetch_hourly(city: str, day: date) -> pd.DataFrame:
    q = sa.text(
        """
        SELECT hour_ts, rainfall_mm
        FROM public.mv_rainfall_hourly
        WHERE city = :city
          AND date(hour_ts) = :d
        ORDER BY hour_ts
        """
    )
    with engine.begin() as conn:
        return rows_to_df(conn.execute(q, {"city": city, "d": day}))


@st.cache_data(ttl=CACHE_TTL_SHORT)
def dry_wet_ratio(city: str, start: date, end: date) -> tuple[int, int]:
    q = sa.text(
        """
        WITH daily AS (
          SELECT date(hour_ts) AS d,
                 SUM(rainfall_mm) AS mm
          FROM public.mv_rainfall_hourly
          WHERE city = :city
            AND hour_ts BETWEEN :start AND :end
          GROUP BY d
        )
        SELECT
          COUNT(*) FILTER (WHERE mm = 0) AS dry_days,
          COUNT(*) FILTER (WHERE mm > 0) AS wet_days
        FROM daily
        """
    )
    with engine.begin() as conn:
        dry, wet = conn.execute(q, {"city": city, "start": start, "end": end}).fetchone()
    return dry, wet

# ---------------------------------------------------------------------------#
# Visualization Fonctions                                                    #
# ---------------------------------------------------------------------------#
def _fill_missing_days(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """Add every day in [start, end] with 0 mm if it’s absent from the query."""
    df = df.copy()
    df["day"] = pd.to_datetime(df["day"])

    all_days = pd.date_range(start, end, freq="D")
    filled   = (
        pd.DataFrame({"day": all_days})
        .merge(df, on="day", how="left")
        .fillna({"total_mm": 0})
    )
    filled["total_mm"] = filled["total_mm"].astype(float)
    return filled

def chart_daily(df: pd.DataFrame) -> alt.Chart:
    max_mm = df["total_mm"].max() or 1.0

    return (
        alt.Chart(df)
        .mark_bar(color="#1f77b4")
        .encode(
            x=alt.X("day:T",
                    title="Day",
                    axis=alt.Axis(format="%Y-%m-%d")),     # date only
            y=alt.Y("total_mm:Q",
                    title="Rainfall (mm)",
                    scale=alt.Scale(domain=[0, max_mm * 1.1]),
                    axis=alt.Axis(format=".2f")),
            tooltip=[alt.Tooltip("day:T"),
                     alt.Tooltip("total_mm:Q", format=".2f")],
        )
        .properties(height=300)
    )


def chart_hourly(df: pd.DataFrame) -> alt.Chart:
    if df.empty:
        return alt.Chart(pd.DataFrame())

    df = df.copy()

    df["rainfall_mm"] = df["rainfall_mm"].astype(float)
    max_mm = df["rainfall_mm"].max() or 1.0

    df["end_hour"]   = pd.to_datetime(df["hour_ts"]).dt.hour
    df["start_hour"] = (df["end_hour"] - 1) % 24
    max_mm = df["rainfall_mm"].astype(float).max() or 1.0

    return (
        alt.Chart(df)
        .mark_bar(color="#1f77b4", orient="vertical")   # force upright bars
        .encode(
            # bar spans the full hour
            x = alt.X("start_hour:Q",
                      title="Hour of day (UTC)",
                      scale = alt.Scale(domain=[0, 24]),
                      axis  = alt.Axis(values=list(range(25)))),
            x2 = "end_hour:Q",

            # rises from 0 up to rainfall_mm automatically
            y = alt.Y("rainfall_mm:Q",
                      title="Rainfall (mm)",
                      scale = alt.Scale(domain=[0, max_mm * 1.1]),
                      axis  = alt.Axis(format=".2f")),

            tooltip = [
                alt.Tooltip("start_hour:Q", title="Start h"),
                alt.Tooltip("end_hour:Q",   title="End h"),
                alt.Tooltip("rainfall_mm:Q", format=".2f"),
            ],
        )
        .properties(height=300)
    )


def chart_drywet(wet: int, dry: int) -> alt.Chart:
    df = pd.DataFrame({
        "Type": ["Wet days", "Dry days"],
        "Count": [wet, dry]
    })

    color_map = {
        "Wet days": "#1f77b4",   # blue
        "Dry days": "#ff7f0e"    # orange
    }

    return (
        alt.Chart(df)
        .mark_arc(innerRadius=50, outerRadius=100)
        .encode(
            theta=alt.Theta("Count:Q"),
            color=alt.Color(
                "Type:N",
                scale=alt.Scale(
                    domain=list(color_map.keys()),
                    range=list(color_map.values())
                )
            ),
            tooltip=["Type:N", "Count:Q"]
        )
        .properties(height=300)
    )

# ---------------------------------------------------------------------------#
# Sidebar                                                                    #
# ---------------------------------------------------------------------------#
st.sidebar.header("Filters")

cities = get_cities()
if not cities:
    st.error("No data yet – run the ETL pipeline first.")
    st.stop()

city = st.sidebar.selectbox("City", options=cities)

today = datetime.utcnow().date()
default_start = today - timedelta(days=30)

start_date = st.sidebar.date_input("Start date", value=default_start, max_value=today)
end_date   = st.sidebar.date_input("End date",   value=today,          min_value=start_date)

# ---------------------------------------------------------------------------#
# Tabs                                                                       #
# ---------------------------------------------------------------------------#
tab_live, tab_daily, tab_hourly, tab_drywet = st.tabs(
    ["💧 Live", "📆 Daily", "🕐 Hourly", "🌤 Dry vs Wet"]
)

# 1. Live
with tab_live:
    st.subheader(f"Live rainfall — {city}")
    val = get_live_rain(city)
    st.metric("Rainfall last hour (mm)", f"{val:.2f}" if val is not None else "–")

# 2. Daily 
with tab_daily:
    st.subheader(f"Daily rainfall in {city}")
    df_day_raw = fetch_daily(city, start_date, end_date)
    df_day = _fill_missing_days(df_day_raw, start_date, end_date)
    if df_day.empty:
        st.info("No data for selected period.")
    else:
        st.altair_chart(chart_daily(df_day), use_container_width=True)
        st.metric("Total mm", f"{df_day['total_mm'].sum():.2f}")
        st.download_button(
            "Download CSV",
            df_day.to_csv(index=False).encode(),
            file_name="rainwise_daily.csv",
        )

# 3. Hourly 
with tab_hourly:
    chosen_day = st.date_input(
        "Choose day", value=today, max_value=today, min_value=start_date, key="day_input"
    )
    st.subheader(f"Hourly rainfall on {chosen_day} — {city}")
    df_hour = fetch_hourly(city, chosen_day)
    if df_hour.empty:
        st.info("No data for that day.")
    else:
    #   st.line_chart(df_hour.set_index("hour_ts"))
        st.altair_chart(chart_hourly(df_hour), use_container_width=True)
        st.caption("Rainfall measured over each hour (UTC)")

# 4. Dry vs Wet
with tab_drywet:
    dry, wet = dry_wet_ratio(city, start_date, end_date)
    total = dry + wet

    st.subheader(f"Dry vs Wet days — {city}")
    if total == 0:
        st.info("No data in this date range.")
    else:
        st.altair_chart(chart_drywet(wet, dry), use_container_width=True)
        st.caption(f"{wet} wet days • {dry} dry days over {total} days")

# ---------------------------------------------------------------------------#
# Footer                                                                     #
# ---------------------------------------------------------------------------#
st.caption(
    "Sources: OpenWeatherMap • Pipeline: Apache Airflow • Validation: Great Expectations • Storage: Postgres + Materialized View"
)