#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent

TOOLS = {
    "1": ("Chay Flask server", "run_server.py"),
    "2": ("Cap nhat IP Flask vao ESP32", "update_server_ip.py"),
    "3": ("Kiem tra backend / device state", "check_backend.py"),
    "4": ("Build ESP32", "build_esp32.py"),
    "5": ("Flash + Serial Monitor", "flash_monitor.py"),
}

def run_script(name):
    path = HERE / name
    if not path.exists():
        print(f"[LOI] Khong tim thay {path}")
        return 1
    return subprocess.run([sys.executable, str(path)]).returncode

while True:
    print("\n" + "=" * 60)
    print("IOT CLASSROOM RESPONSE - MENU")
    print("=" * 60)
    for key, (label, _) in TOOLS.items():
        print(f"{key}. {label}")
    print("6. Quy trinh nhanh: cap nhat IP -> build -> flash")
    print("0. Thoat")

    choice = input("\nChon: ").strip()

    if choice == "0":
        break
    elif choice in TOOLS:
        run_script(TOOLS[choice][1])
    elif choice == "6":
        for filename in ["update_server_ip.py", "build_esp32.py", "flash_monitor.py"]:
            code = run_script(filename)
            if code != 0:
                print(f"\nDung quy trinh vi {filename} bi loi.")
                break
    else:
        print("Lua chon khong hop le.")
