#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

PROJECT = Path.home() / "IOT"
ACTIVATE = Path.home() / "esp" / "esp-idf" / "export.sh"

if not PROJECT.exists():
    print(f"[LOI] Khong tim thay project: {PROJECT}")
    sys.exit(1)

if not ACTIVATE.exists():
    print(f"[LOI] Khong tim thay ESP-IDF activate script: {ACTIVATE}")
    sys.exit(1)

cmd = f'source "{ACTIVATE}" && cd "{PROJECT}" && idf.py build'

print("=" * 60)
print("BUILD ESP32")
print("=" * 60)

result = subprocess.run(["bash", "-lc", cmd])
sys.exit(result.returncode)
