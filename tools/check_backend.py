#!/usr/bin/env python3
import json
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:5000"
MSSV = input("Nhap MSSV de test [22123456]: ").strip() or "22123456"

def get(path):
    url = BASE + path
    print(f"\nGET {url}")
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            body = r.read().decode("utf-8", errors="replace")
            print(f"HTTP {r.status}")
            try:
                print(json.dumps(json.loads(body), ensure_ascii=False, indent=2))
            except Exception:
                print(body)
            return True
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}")
        print(e.read().decode("utf-8", errors="replace"))
    except Exception as e:
        print(f"[LOI] {e}")
    return False

print("=" * 60)
print("KIEM TRA FLASK BACKEND")
print("=" * 60)

if get("/api/overview"):
    get(f"/device/state?mssv={MSSV}")
else:
    print("\nFlask co ve chua chay. Hay chay run_server.py truoc.")
