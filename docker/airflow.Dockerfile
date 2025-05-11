# ─────────────────────────────────────────────────────────────
# BASE IMAGE
# Use the official Airflow image (Python 3.11 build) as the base.
# ─────────────────────────────────────────────────────────────
FROM apache/airflow:2.9.0-python3.11

# ─────────────────────────────────────────────────────────────
# OS-LEVEL DEPENDENCIES
# Switch to root, install a minimal build toolchain (needed if
# any Python wheels require compilation), then clean up.
# ─────────────────────────────────────────────────────────────
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# ─────────────────────────────────────────────────────────────
# PYTHON LIBRARIES
# Drop back to the non-root airflow user and install all Python
# dependencies listed in requirements.txt (pandas, GE, etc).
# ─────────────────────────────────────────────────────────────
USER airflow
COPY requirements.txt /tmp/reqs.txt
RUN pip install --no-cache-dir -r /tmp/reqs.txt

# ─────────────────────────────────────────────────────────────
# DAG CODE
# Copy DAGs into the image so a production deployment (e.g. MWAA)
# sees them even without a volume mount. In local dev this path is
# over-mounted, so hot-reload still works.
# ─────────────────────────────────────────────────────────────
COPY dags/ /opt/airflow/dags