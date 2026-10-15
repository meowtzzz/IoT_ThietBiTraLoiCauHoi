IOT TOOLS

Chep thu muc nay vao, vi du:
    ~/IOT/tools/

Sau do:
    cd ~/IOT/tools
    python3 iot_manager.py

Hoac chay tung file:
    python3 run_server.py
    python3 update_server_ip.py
    python3 check_backend.py
    python3 build_esp32.py
    python3 flash_monitor.py

GOI Y DUNG

Terminal 1:
    python3 run_server.py

Giu terminal nay mo de Flask chay.

Terminal 2:
    python3 iot_manager.py

Chon:
    2 -> cap nhat IP server vao http_client.c
    3 -> test backend
    4 -> build
    5 -> flash + monitor

Dashboard:
    http://127.0.0.1:5000

LUU Y
- run_server.py dung truc tiep Python trong ~/IOT/server/venv, khong can source venv.
- build/flash tu dong source ~/.espressif/tools/activate_idf_v6.1.sh.
- flash_monitor.py tu tim /dev/ttyUSB* va /dev/ttyACM*.
- update_server_ip.py tu cap nhat ANSWER_URL va STATE_URL trong ~/IOT/main/http_client.c.
