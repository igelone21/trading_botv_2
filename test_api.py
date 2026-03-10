import requests
from config import Config

base = Config.get_api_url()
key = Config.IG_API_KEY

r = requests.post(f"{base}/session", json={"identifier": Config.IG_USERNAME, "password": Config.IG_PASSWORD},
    headers={"Content-Type": "application/json", "X-IG-API-KEY": key, "Version": "2"}, timeout=10)
r.raise_for_status()
cst = r.headers["CST"]
token = r.headers["X-SECURITY-TOKEN"]
print("Login OK, Account:", r.json().get("currentAccountId"))
print("Account Type:", r.json().get("accountType"))
print("Accounts:", [a.get("accountId") + "/" + a.get("accountType","") for a in r.json().get("accounts",[])])

h = {"X-IG-API-KEY": key, "CST": cst, "X-SECURITY-TOKEN": token, "Content-Type": "application/json", "Version": "1"}

# Test verschiedene DAX epics
epics = ["IX.D.DAX.IFD.IP", "IX.D.DAX.CASH.IP", "IX.D.DAX.DAILY.IP", "CC.D.DAX.USS.IP"]
for epic in epics:
    resp = requests.get(f"{base}/markets/{epic}", headers=h, timeout=10)
    print(f"markets/{epic} → {resp.status_code}")
    if resp.status_code == 200:
        snap = resp.json().get("snapshot", {})
        print(f"  Bid: {snap.get('bid')} Offer: {snap.get('offer')}")
