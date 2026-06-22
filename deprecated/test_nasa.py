import requests
url = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
query = "select pl_name, hostname from ps where pl_name='Kepler-90 b'"
params = {"query": query, "format": "json"}
resp = requests.get(url, params=params)
if resp.ok:
    data = resp.json()
    print(f"Got {len(data)} rows")
    if data:
        print("First:", data[0])
else:
    print("Error:", resp.text)
