#!/usr/bin/env python3
from pathlib import Path
import glob
import subprocess
import sys

PROJECT = Path.home() / "IOT"
ACTIVATE = Path.home() / "esp" / "esp-idf" / "export.sh"

def find_ports():
    return sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))

if not PROJECT.exists():
    print(f"[LOI] Khong tim thay project: {PROJECT}")
    sys.exit(1)

if not ACTIVATE.exists():
    print(f"[LOI] Khong tim thay ESP-IDF activate script: {ACTIVATE}")
    sys.exit(1)

ports = find_ports()
if not ports:
    print("[LOI] Khong tim thay ESP32 o /dev/ttyUSB* hoac /dev/ttyACM*")
    print("Thu rut/cam lai cap USB roi chay lai file nay.")
    sys.exit(1)

if len(ports) == 1:
    port = ports[0]
else:
    print("Tim thay nhieu cong serial:")
    for i, p in enumerate(ports, 1):
        print(f"{i}. {p}")
    try:
        choice = int(input("Chon cong: ").strip())
        port = ports[choice - 1]
    except (ValueError, IndexError):
        print("[LOI] Lua chon khong hop le.")
        sys.exit(1)

print("=" * 60)
print("FLASH + MONITOR ESP32")
print("=" * 60)
print(f"Port: {port}")
print("Thoat monitor: Ctrl+]")
print()

cmd = f'source "{ACTIVATE}" && cd "{PROJECT}" && idf.py -p "{port}" flash monitor'
result = subprocess.run(["bash", "-lc", cmd])
sys.exit(result.returncode)
