#!/usr/bin/env python3
from pathlib import Path
import re
import socket
import subprocess
import sys

HTTP_FILE = Path.home() / "IOT" / "main" / "http_client.c"

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass

    try:
        out = subprocess.check_output(["hostname", "-I"], text=True)
        for ip in out.split():
            if "." in ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass

    return None

if not HTTP_FILE.exists():
    print(f"[LOI] Khong tim thay: {HTTP_FILE}")
    sys.exit(1)

ip = get_local_ip()
if not ip:
    print("[LOI] Khong tu dong xac dinh duoc IPv4 cua laptop.")
    print("Hay chay: hostname -I")
    sys.exit(1)

text = HTTP_FILE.read_text(encoding="utf-8")
old = text

answer_line = f'#define ANSWER_URL "http://{ip}:5000/answer"'
state_line = f'#define STATE_URL "http://{ip}:5000/device/state"'

text, n_answer = re.subn(
    r'^\s*#define\s+ANSWER_URL\s+"[^"]*"\s*$',
    answer_line,
    text,
    flags=re.MULTILINE,
)

if n_answer == 0:
    text, n_server = re.subn(
        r'^\s*#define\s+SERVER_URL\s+"[^"]*"\s*$',
        answer_line,
        text,
        count=1,
        flags=re.MULTILINE,
    )
    n_answer = n_server

text, n_state = re.subn(
    r'^\s*#define\s+STATE_URL\s+"[^"]*"\s*$',
    state_line,
    text,
    flags=re.MULTILINE,
)

if n_answer == 0 or n_state == 0:
    print("[LOI] Khong tim thay ANSWER_URL/SERVER_URL hoac STATE_URL trong http_client.c.")
    print("Khong ghi file de tranh sua sai.")
    sys.exit(1)

if text != old:
    HTTP_FILE.write_text(text, encoding="utf-8")

print("=" * 60)
print("CAP NHAT IP SERVER CHO ESP32")
print("=" * 60)
print(f"IP laptop : {ip}")
print(f"ANSWER_URL: http://{ip}:5000/answer")
print(f"STATE_URL : http://{ip}:5000/device/state")
print(f"Da cap nhat: {HTTP_FILE}")
