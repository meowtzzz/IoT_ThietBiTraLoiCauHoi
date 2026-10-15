#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

PROJECT = Path.home() / "IOT"
SERVER_DIR = PROJECT / "server"
VENV_PYTHON = SERVER_DIR / "venv" / "bin" / "python"
SERVER_FILE = SERVER_DIR / "server.py"

if not SERVER_FILE.exists():
    print(f"[LOI] Khong tim thay: {SERVER_FILE}")
    sys.exit(1)

python_cmd = str(VENV_PYTHON) if VENV_PYTHON.exists() else "python3"

print("=" * 60)
print("KHOI DONG FLASK SERVER")
print("=" * 60)
print(f"Thu muc : {SERVER_DIR}")
print(f"Python  : {python_cmd}")
print("Dashboard local: http://127.0.0.1:5000")
print("Nhan Ctrl+C de dung server.")
print()

try:
    subprocess.run([python_cmd, str(SERVER_FILE)], cwd=SERVER_DIR, check=False)
except KeyboardInterrupt:
    print("\nDa dung Flask server.")
