# ─────────────────────────────────────────────────────────────
# BASE IMAGE
# Lightweight Python 3.11 image for the dashboard layer.
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

# ─────────────────────────────────────────────────────────────
# WORKDIR
# Everything that follows happens under /app inside the container.
# ─────────────────────────────────────────────────────────────
WORKDIR /app

# ─────────────────────────────────────────────────────────────
# PYTHON LIBRARIES
# Install only what the Streamlit front-end needs.
# ─────────────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir streamlit pandas requests

# ─────────────────────────────────────────────────────────────
# APP SOURCE
# Copy the Streamlit app code into the container image.
# ─────────────────────────────────────────────────────────────
COPY streamlit_app/ .

# ─────────────────────────────────────────────────────────────
# NETWORK
# Expose the default Streamlit port so Docker can map it.
# ─────────────────────────────────────────────────────────────
EXPOSE 8501

# ─────────────────────────────────────────────────────────────
# STARTUP COMMAND
# Launch the Streamlit development server when the container runs.
# ─────────────────────────────────────────────────────────────
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.enableCORS=false"]