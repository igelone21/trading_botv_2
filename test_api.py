import requests
from config import Config

base = Config.get_api_url()
key = Config.IG_API_KEY

r = requests.post(f"{base}/session", json={"identifier": Config.IG_USERNAME, "password": Config.IG_PASSWORD},
    headers={"Content-Type": "application/json", "X-IG-API-KEY": key, "Version": "2"}, timeout=10)
r.raise_for_status()
cst = r.headers["CST"]
token = r.headers["X-SECURITY-TOKEN"]
print("Login OK")

h = {"X-IG-API-KEY": key, "CST": cst, "X-SECURITY-TOKEN": token, "Content-Type": "application/json", "Version": "1"}

# Suche nach Deutschland/DAX
resp = requests.get(f"{base}/markets?searchTerm=Deutschland+40", headers=h, timeout=10)
print(f"Suche → {resp.status_code}")
if resp.status_code == 200:
    for m in resp.json().get("markets", []):
        print(f"  Epic: {m.get('epic')} | Name: {m.get('instrumentName')} | Type: {m.get('instrumentType')}")
