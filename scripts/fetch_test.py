import os, requests, json, pathlib, time

# ──────────── 1. Grab API credentials safely ────────────
API_KEY = os.getenv("OWM_API_KEY")        # reads from env variable

if not API_KEY:
    raise EnvironmentError(
        "OWM_API_KEY not found. Did you create .env and load it?"
    )

# ──────────── 2. Build the request URL ────────────
CITY = "Biarritz"
COUNTRY_CODE = "FR"
url = (
    #"https://api.openweathermap.org/data/2.5/weather"f"?{lAT}&{lON}&appid={API_KEY}&units=metric"  #normal use of current weather API, giving weather conditions
    #"http://api.openweathermap.org/geo/1.0/direct"f"?q={CITY},{COUNTRY_CODE}&appid={API_KEY}"      #normal use of geocoding API, giving LAT and LONG
    "https://api.openweathermap.org/data/2.5/weather"f"?q={CITY},{COUNTRY_CODE}&appid={API_KEY}&units=metric" #Integrated geocoding (deprecated)
)

# ──────────── 3. Call the API ────────────
resp = requests.get(url, timeout=10)
resp.raise_for_status()                   # fails fast on HTTP errors
data = resp.json()                        # dict with weather info

# ──────────── 4. Extract rainfall safely ────────────
rain_mm = data.get("rain", {}).get("1h", 0.0)  # default to 0 mm if missing

# ──────────── 5. Build a tidy payload ────────────
payload = {
    "city": CITY,
    "timestamp": data["dt"],                      # Unix epoch
    "datetime_iso": time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(data["dt"])
    ),
    "rainfall_mm": rain_mm,
}

# ──────────── 6. Ensure target directory exists ────────────
raw_dir = pathlib.Path("data", "raw")
raw_dir.mkdir(parents=True, exist_ok=True)

# ──────────── 7. Persist to JSON (raw landing zone) ─────────
out_path = raw_dir / "sample.json"
with out_path.open("w") as fp:
    json.dump(payload, fp, indent=2)

print(f"Wrote {out_path} :", json.dumps(payload, indent=2))