# one-off-geocode.py (run this interactively or as a script)
import pandas as pd, json, os
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

df = pd.read_csv("stakeholders.csv", encoding="latin-1")
df = df[df.Country.notna() & (df.Country!="")].copy()
df["Location"] = df.apply(
    lambda r: f"{r.City}, {r.Country}" if pd.notna(r.City) and r.City!="" else r.Country,
    axis=1
)

cache = {}
geolocator = Nominatim(user_agent="extrusion_map")
geocode    = RateLimiter(geolocator.geocode, min_delay_seconds=1, max_retries=3)

for loc in df["Location"].unique():
    res = geocode(loc, timeout=10)
    cache[loc] = (res.latitude, res.longitude) if res else (None, None)

with open("geocoded_cache.json", "w") as f:
    json.dump(cache, f, indent=2)
print("Cache written! Now disable live geocoding in app.py.")

