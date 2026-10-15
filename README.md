# Thiết bị trả lời câu hỏi IoT với ESP32

Project hỗ trợ giảng viên tổ chức bài kiểm tra trắc nghiệm và nhận đáp án từ thiết bị ESP32. Sinh viên nhập mã số sinh viên (MSSV), chọn đáp án bằng keypad 4×4 và xem trạng thái trên màn hình OLED. Giảng viên quản lý lớp, bài kiểm tra, phiên làm bài và kết quả trên dashboard web.

Tài liệu này hướng dẫn cài đặt trên **Ubuntu**, từ một bản clone mới đến khi gửi được đáp án đầu tiên. Các lệnh giả định project nằm tại **`~/IOT`** và ESP-IDF nằm tại **`~/esp/esp-idf`**.

## 1. Project hoạt động như thế nào?

```text
Keypad + OLED → ESP32 → Wi-Fi/LAN → Flask trên laptop:5000 → MariaDB
                                          ↑
                                  Trình duyệt dashboard
```

- ESP32 kết nối Wi-Fi và nhận địa chỉ IP qua DHCP.
- Sau khi xác nhận MSSV, ESP32 định kỳ gọi `GET /device/state?mssv=...` để biết phiên và câu hỏi hiện tại.
- Khi sinh viên chọn đáp án rồi nhấn `#`, ESP32 gửi `POST /answer`.
- Flask ghi đáp án vào MariaDB; dashboard cập nhật danh sách và thống kê.
- Laptop chạy Flask phải được bật và có kết nối mạng tới ESP32 trong suốt phiên làm bài.

## 2. Cần chuẩn bị gì?

### Phần mềm

| Thành phần | Môi trường tham chiếu |
| --- | --- |
| Hệ điều hành | Ubuntu 24.04 |
| Python | 3.12 |
| ESP-IDF | v6.1, target `esp32` |
| Database | MariaDB 10.11 |
| Backend | Flask; package nằm trong `server/requirements.txt` |
| Dashboard | Trình duyệt web; không cần Node.js |

Cần Internet để tải source, SDK và package trong lần cài đầu. Khi chạy thử, ESP32 và server giao tiếp qua mạng LAN.

### Phần cứng và mạng

- Board ESP32 phù hợp target `esp32` của project, chẳng hạn board dùng module ESP32-WROOM-32.
- Keypad ma trận **4×4**, có các phím số, `A/B/C/D`, `*`, `#`.
- OLED **SSD1306 I2C 128×32**, địa chỉ `0x3C` hoặc `0x3D`.
- Cáp USB có truyền dữ liệu và dây nối.
- Wi-Fi **2.4 GHz** cho ESP32. Laptop có thể dùng Wi-Fi hoặc Ethernet, miễn truy cập được từ mạng của ESP32.

Nếu đã có nguyên bộ đấu dây sẵn và hoạt động đúng, giữ nguyên cách đấu dây. **Ngắt USB và mọi nguồn ngoài trước khi đổi dây.**

### Sơ đồ GPIO theo source hiện tại

| Đường tín hiệu | Các phím cùng hàng/cột | GPIO ESP32 |
| --- | --- | --- |
| Keypad R1 | `1 2 3 A` | 14 |
| Keypad R2 | `4 5 6 B` | 27 |
| Keypad R3 | `7 8 9 C` | 26 |
| Keypad R4 | `* 0 # D` | 25 |
| Keypad C1 | `1 4 7 *` | 33 |
| Keypad C2 | `2 5 8 0` | 32 |
| Keypad C3 | `3 6 9 #` | 21 |
| Keypad C4 | `A B C D` | 22 |
| OLED SDA | — | 18 |
| OLED SCL | — | 19 |

Nối GND chung; cấp nguồn OLED theo thông số module, bảo đảm các tín hiệu nối ESP32 dùng mức logic 3.3 V. Đối chiếu sơ đồ chân của keypad để xác định R1–R4/C1–C4: **không mặc định chân vật lý 1–8 luôn có cùng thứ tự ở mọi model**.

## 3. Cài các gói Ubuntu

```bash
sudo apt update
sudo apt install git wget flex bison gperf build-essential python3 python3-pip \
  python3-venv cmake ninja-build ccache libffi-dev libssl-dev dfu-util \
  libusb-1.0-0 mariadb-server mariadb-client curl
```

Các bước sau dùng Bash, shell mặc định trên nhiều bản Ubuntu.

## 4. Tải project về đúng vị trí

Nếu chưa có project:

```bash
cd ~
git clone https://github.com/meowtzzz/IoT_ThietBiTraLoiCauHoi.git IOT
cd ~/IOT
```

Nếu repository là Private, cần tài khoản được cấp quyền. Có thể đăng nhập bằng GitHub CLI trước khi clone:

```bash
sudo apt install gh
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
```

Nếu đã có `~/IOT`, bỏ qua lệnh clone và mở folder đó. Không clone đè lên bản đang làm việc.

Các script trong `tools` dùng `Path.home() / "IOT"`. Ví dụ, với tài khoản `mtee`, project được tìm tại `/home/mtee/IOT`; tài khoản khác sẽ dùng thư mục home tương ứng. Nếu đặt project ở nơi khác, cần tự sửa các đường dẫn `PROJECT`/`HTTP_FILE` trong script, hoặc dùng lệnh trực tiếp từ đúng folder project.

## 5. Cài ESP-IDF v6.1

Nếu chưa có SDK tại `~/esp/esp-idf`:

```bash
mkdir -p ~/esp
cd ~/esp
git clone --branch v6.1 --single-branch --recursive https://github.com/espressif/esp-idf.git esp-idf
cd ~/esp/esp-idf
./install.sh esp32
```

Nếu đã có SDK, không clone lần nữa; kiểm tra phiên bản và cài bổ sung tool nếu script kích hoạt báo thiếu.

Kích hoạt ESP-IDF trong terminal cần dùng lệnh `idf.py`:

```bash
source "$HOME/esp/esp-idf/export.sh"
idf.py --version
```

Kết quả cần là ESP-IDF v6.1. Khi mở terminal mới để chạy `idf.py` trực tiếp, cần kích hoạt lại. Script build/flash trong project tự thực hiện bước kích hoạt trong subprocess của nó.

Cấu hình hiện tại của hai script `tools/build_esp32.py` và `tools/flash_monitor.py` là:

```python
ACTIVATE = Path.home() / "esp" / "esp-idf" / "export.sh"
```

Nếu SDK cài ở nơi khác, đổi `ACTIVATE` trong **cả hai file** tới script kích hoạt đúng trên máy. Tài liệu `tools/README.txt` cũ còn nhắc một đường dẫn kích hoạt khác; đối chiếu source script hiện tại khi cấu hình.

## 6. Tạo môi trường Python cho server

Trong một terminal bình thường, tạo môi trường riêng cho Flask:

```bash
cd ~/IOT
/usr/bin/python3 -m venv server/venv
./server/venv/bin/python -m pip install -r server/requirements.txt
./server/venv/bin/python -c "import flask, mysql.connector; print('Python server OK')"
```

Nếu thành công, lệnh cuối in `Python server OK`.

Không dùng lại `venv` chép từ máy khác. Nếu nhận project bằng cách copy folder và đã có `server/venv` cũ, đổi tên folder cũ sang một tên backup chưa tồn tại rồi tạo lại môi trường như trên.

Không cần kích hoạt `server/venv` thủ công khi dùng `tools/run_server.py`: script tự gọi Python tại `~/IOT/server/venv/bin/python`.

## 7. Tạo database lần đầu

### 7.1. Khởi động MariaDB

```bash
sudo systemctl start mariadb
sudo systemctl is-active mariadb
```

Kết quả cần là `active`.

### 7.2. Tạo database mới và tài khoản ứng dụng

Ví dụ dưới đây dùng database `esp32_db`, tài khoản `esp32app`, kết nối TCP tới `127.0.0.1`. Có thể chọn tên khác, nhưng phải đổi nhất quán trong SQL và các biến môi trường khi chạy Flask.

Mở MariaDB bằng tài khoản quản trị:

```bash
sudo mariadb
```

Nhập SQL sau. Thay `CHANGE_ME_DB_PASSWORD` bằng mật khẩu database do bạn chọn:

```sql
CREATE DATABASE esp32_db
  CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;

CREATE USER 'esp32app'@'127.0.0.1'
  IDENTIFIED BY 'CHANGE_ME_DB_PASSWORD';

GRANT SELECT, INSERT, UPDATE, DELETE
  ON esp32_db.* TO 'esp32app'@'127.0.0.1';

EXIT;
```

Nếu database hoặc user đã tồn tại, kiểm tra cấu hình đang có trước khi tiếp tục. Với một bản cài đang hoạt động, dùng lại database/user hiện tại; không cần tạo lại. Mật khẩu database độc lập với mật khẩu Wi-Fi.

### 7.3. Import cấu trúc cho database mới

Chỉ chạy lệnh sau với database mới, chưa chứa dữ liệu cần giữ:

```bash
cd ~/IOT
sudo mariadb esp32_db < server/database/schema.sql
sudo mariadb esp32_db -e "SHOW TABLES;"
```

Cần có các bảng như `classes`, `class_students`, `students`, `quizzes`, `questions`, `quiz_sessions`, `responses`, `quiz_state`.

`schema.sql` chứa cấu trúc hiện tại, không có dữ liệu lớp/câu hỏi/sinh viên mẫu. Một số bảng tên `*_backup` cũng được tạo nhưng không chứa dữ liệu backup. Khi bắt đầu phiên đầu tiên, backend tự tạo bản ghi trạng thái phiên nếu chưa có.

**File schema có `DROP TABLE`: không import lại vào database đang có dữ liệu cần giữ. Sau khi import schema hiện tại, không chạy `migration_v2.sql`.**

`migration_v2.sql` chỉ dành cho nâng cấp database phiên bản cũ: cần backup trước và chỉ chạy một lần theo hướng dẫn của phiên bản đó. Người mới clone repository dùng `schema.sql` ở bước này.

Kiểm tra tài khoản ứng dụng; nhập mật khẩu database khi được hỏi:

```bash
mariadb --protocol=tcp -h 127.0.0.1 -u esp32app -p esp32_db -e "SHOW TABLES;"
```

## 8. Cấu hình Wi-Fi và IP server

### 8.1. Đổi Wi-Fi trong firmware

Kết nối laptop vào mạng có thể giao tiếp với ESP32. Với cách thử đơn giản, dùng cùng mạng LAN và tránh mạng khách có tính năng cô lập thiết bị.

Mở [main/main.c](main/main.c), tìm `wifi_connect(...)` trong `app_main()` và sửa:

```c
wifi_connect("TEN_WIFI_CUA_BAN", "MAT_KHAU_WIFI_CUA_BAN");
```

Đây là cấu hình Wi-Fi thực tế của project; thay tên Wi-Fi và mật khẩu rồi lưu file. Nếu chuỗi chứa dấu `"` hoặc `\`, phải viết escape đúng theo cú pháp chuỗi C.

ESP32 chờ tới khi kết nối Wi-Fi và nhận IP mới tiếp tục vào màn hình nhập MSSV. Sai thông tin Wi-Fi có thể khiến OLED dừng ở `KET NOI WIFI...` và log liên tục báo kết nối lại.

### 8.2. Lấy IP LAN của laptop

```bash
ip -4 -brief address
```

Tìm IPv4 của interface đang kết nối tới mạng ESP32, chẳng hạn `wlp...` cho Wi-Fi hoặc `enp...` cho Ethernet. Ví dụ `192.168.1.25/24` nghĩa là IP laptop `192.168.1.25`.

| Địa chỉ | Ý nghĩa |
| --- | --- |
| `127.0.0.1:5000` | Truy cập Flask ngay trên laptop chạy server |
| `IP_LAN_LAPTOP:5000` | Địa chỉ ESP32 và thiết bị khác dùng để truy cập Flask |
| `0.0.0.0` trong cấu hình Flask | Lắng nghe trên các interface mạng của laptop |
| IP được in sau `IP ESP32:` | Địa chỉ của ESP32, không phải địa chỉ server |

### 8.3. Đổi cả hai URL trong firmware

Mở [main/http_client.c](main/http_client.c). Nếu laptop có IP `192.168.1.25`, sửa thành:

```c
#define ANSWER_URL "http://192.168.1.25:5000/answer"
#define STATE_URL "http://192.168.1.25:5000/device/state"
```

Thay IP minh họa bằng IP thực tế. Giữ nguyên cổng `5000` và đường dẫn của từng API. Không đặt `127.0.0.1` hay `0.0.0.0` làm địa chỉ server trong firmware.

Có thể tự động cập nhật bằng:

```bash
cd ~/IOT
python3 tools/update_server_ip.py
```

**Script này ghi sửa hai URL trong source**, không đổi Wi-Fi và không nạp thiết bị. Nếu có VPN hoặc nhiều interface, kiểm tra IP được chọn trước khi build.

Mỗi lần đổi Wi-Fi, IP server hoặc code firmware, phải lưu file, build và nạp lại ESP32 để thiết bị nhận thay đổi.

## 9. Cấp quyền truy cập USB serial

Cắm ESP32 bằng cáp USB truyền dữ liệu. Kiểm tra cổng:

```bash
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
```

Cổng thường là `/dev/ttyUSB0` hoặc `/dev/ttyACM0`; tên có thể đổi khi rút/cắm. Trên Ubuntu, nếu cổng thuộc nhóm `dialout`, thêm user hiện tại vào nhóm:

```bash
sudo usermod -aG dialout "$USER"
```

Đăng xuất Ubuntu rồi đăng nhập lại để quyền có hiệu lực. Đóng/mở terminal có thể chưa đủ. Nếu muốn áp dụng ngay cho một terminal, chạy `newgrp dialout`, rồi chạy lệnh nạp trong chính terminal đó.

Kiểm tra:

```bash
id -nG
ls -l /dev/ttyUSB0
```

Danh sách nhóm cần có `dialout` nếu cổng đang thuộc nhóm đó. Thay tên cổng trong lệnh kiểm tra nếu cần.

## 10. Chạy Flask và kiểm tra backend

### Terminal 1: chạy server

```bash
cd ~/IOT
export DB_HOST=127.0.0.1
export DB_NAME=esp32_db
export DB_USER=esp32app
read -r -s -p "Mat khau database: " DB_PASSWORD
printf '\n'
export DB_PASSWORD
python3 tools/run_server.py
```

Nhập mật khẩu đã chọn ở bước tạo tài khoản database. Nếu dùng tên database/user khác, thay giá trị tương ứng. Ví dụ một bản cài trước có thể dùng `DB_NAME=esp32_db_mtee`, `DB_USER=iot_mtee`.

`read -s` không hiện ký tự mật khẩu khi nhập. Giữ Terminal 1 mở; `Ctrl+C` sẽ dừng Flask.

Các biến `DB_*` chỉ có hiệu lực trong terminal đã export và các tiến trình con. Khi chạy server từ terminal mới, cần cấu hình lại. Server hiện không tự đọc file `.env`.

Mở dashboard bằng trình duyệt trên laptop:

```text
http://127.0.0.1:5000
```

Nếu chạy trực tiếp thay vì dùng tool, vẫn cấu hình các biến `DB_*` ở trên rồi dùng:

```bash
cd ~/IOT
./server/venv/bin/python server/server.py
```

### Terminal 2: kiểm tra API

```bash
cd ~/IOT
python3 tools/check_backend.py
```

Nhấn Enter để dùng MSSV mặc định `22123456`. Cần nhận HTTP 200 từ `/api/overview` và `/device/state?mssv=...`. Khi chưa có phiên đang hoạt động, JSON sau là bình thường:

```json
{"active": false}
```

Dashboard tải được HTML chưa đủ để xác nhận database hoạt động; `/api/overview` thành công mới xác nhận được phần đọc database.

### Kiểm tra truy cập qua LAN

Trên điện thoại hoặc thiết bị khác cùng LAN, mở URL theo IP laptop, ví dụ:

```text
http://192.168.1.25:5000/api/overview
```

Cần thấy JSON. Nếu localhost hoạt động nhưng thiết bị khác không truy cập được, kiểm tra IP, firewall và tính năng client/AP isolation trên Wi-Fi.

Kiểm tra UFW trên Ubuntu:

```bash
sudo ufw status
```

Nếu UFW đang bật và chặn cổng 5000, có thể cho phép subnet LAN truy cập. Ví dụ **chỉ áp dụng khi mạng thực tế là `192.168.1.0/24`**:

```bash
sudo ufw allow from 192.168.1.0/24 to any port 5000 proto tcp
```

Dùng subnet thực tế theo IP và subnet mask của mạng; không sao chép subnet ví dụ cho mọi mạng.

## 11. Build, nạp và xem log ESP32

Giữ Flask chạy trong Terminal 1. Trong Terminal 2:

```bash
cd ~/IOT
python3 tools/build_esp32.py
python3 tools/flash_monitor.py
```

Chỉ chạy lệnh flash sau khi build thành công. `flash_monitor.py` tự tìm `/dev/ttyUSB*` và `/dev/ttyACM*`; nếu có nhiều cổng, chọn cổng đúng của ESP32. Không mở hai chương trình đọc cùng cổng serial cùng lúc.

Cách tương đương bằng lệnh ESP-IDF trực tiếp, thay cổng theo máy:

```bash
cd ~/IOT
source "$HOME/esp/esp-idf/export.sh"
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
```

`flash` cũng tự build nếu cần. Target của project là `esp32`; không đổi sang ESP32-C3/S3 chỉ để thử nếu đang dùng bộ phần cứng dành cho ESP32 hiện tại.

### Nếu bị kẹt tại `Connecting...`

1. Khi thấy `Connecting...`, nhấn và giữ **BOOT** trên board.
2. Trong khi giữ BOOT, nhấn rồi thả **EN/RST** để reset.
3. Tiếp tục giữ BOOT tới khi hiện thông tin chip hoặc bắt đầu nạp, rồi thả BOOT.
4. Chờ nạp hoàn tất; tránh ngắt cáp khi đang ghi firmware.

Nếu vẫn không kết nối, thử cáp/cổng USB khác, cắm trực tiếp laptop và đóng các serial monitor khác. Có thể thử tốc độ thấp hơn trong terminal đã kích hoạt ESP-IDF:

```bash
idf.py -p /dev/ttyUSB0 -b 115200 flash monitor
```

Sau khi nạp và kết nối Wi-Fi thành công, log cần có các thông báo tương tự:

```text
WIFI: Ket noi WiFi thanh cong!
WIFI: IP ESP32: ...
MAIN: WiFi da san sang!
MAIN: Keypad da san sang!
MAIN: Nhap MSSV, sau do nhan # de xac nhan
```

OLED hiện **`NHAP MSSV`**. Đây là trạng thái thiết bị sẵn sàng nhận MSSV; kết nối tới Flask sẽ được thử sau khi xác nhận MSSV.

Nhấn **Ctrl + ]** để thoát monitor. Thoát monitor không tắt ESP32; thiết bị tiếp tục chạy khi còn nguồn.

## 12. Thử toàn bộ project

### Tạo lớp và bài kiểm tra trên dashboard

1. Mở `http://127.0.0.1:5000` trên laptop.
2. Vào **Lớp học → Tạo lớp mới**, nhập mã lớp và tên lớp.
3. **Mở lớp → Tạo bài kiểm tra**, nhập tên bài.
4. Tạo hai câu mẫu dưới đây, nhập đủ bốn lựa chọn và đáp án đúng.
5. Bấm **Lưu bài kiểm tra → Bắt đầu** để mở phiên trực tiếp.

| Câu hỏi | A | B | C | D | Đúng |
| --- | --- | --- | --- | --- | --- |
| 2 + 2 bằng bao nhiêu? | 3 | 4 | 5 | 6 | B |
| 5 × 5 bằng bao nhiêu? | 20 | 24 | 25 | 30 | C |

Giữ màn hình **Phiên trực tiếp** khi thử. Nếu chuyển sang trang khác bằng menu trong ứng dụng, giao diện có thể hỏi kết thúc phiên; xác nhận sẽ kết thúc phiên đó. Phiên đang hoạt động tự nhận đáp án, không cần thao tác `open/close` riêng.

### Nhập MSSV và gửi đáp án trên keypad

| Thao tác | Kết quả mong đợi |
| --- | --- |
| Nhập `22123456`, nhấn `#` | Xác nhận MSSV và đồng bộ câu hiện tại |
| Nhấn `B` ở câu 1 | OLED hiện `DA CHON: B`, chưa gửi |
| Nhấn `#` | Gửi đáp án; thành công hiện `DA TRA LOI: B` |
| Bấm **Câu tiếp** trên dashboard | OLED chuyển câu sau lần polling tiếp theo, khoảng 1 giây khi mạng tốt |
| Nhấn `C`, rồi `#` ở câu 2 | Dashboard ghi nhận đáp án đúng của câu 2 |
| Nhấn `*` khi đang trả lời | Quay về nhập MSSV để đổi sinh viên |

Trong màn hình `NHAP MSSV`, chỉ nhập chữ số, tối đa 20 ký tự. `*` xóa toàn bộ MSSV đang nhập; A/B/C/D được bỏ qua ở màn hình này.

Khi gửi thành công, log ESP32 có:

```text
POST /answer tra HTTP 200
Server da nhan dap an ...
```

Dashboard cần hiện đúng MSSV và đáp án trong danh sách trả lời. Đây là mốc xác nhận đường truyền **keypad → ESP32 → Flask → database → dashboard** hoạt động.

Backend tự tạo sinh viên và ghi danh vào lớp khi nhận đáp án hợp lệ; không bắt buộc thêm MSSV thủ công trước. Mỗi MSSV chỉ gửi một đáp án cho mỗi câu trong một phiên. Muốn làm lại cùng MSSV/câu, bắt đầu phiên mới.

Có thể nhấn `*`, nhập MSSV khác và gửi một đáp án sai để thử thống kê. Nhãn `ESP32 sẵn sàng` trên dashboard là nội dung giao diện cố định, không phải phép kiểm tra thiết bị đang online.

### Kết thúc và xem kết quả

Bấm **Kết thúc phiên**, xác nhận, rồi vào **Kết quả** để xem kết quả phiên. ESP32 sẽ đồng bộ về trạng thái chờ phiên mới.

## 13. Sử dụng lại vào lần sau

Nếu Wi-Fi, IP server và code firmware không đổi, không cần cài lại package, import schema hoặc nạp lại ESP32.

1. Kết nối laptop vào mạng có thể truy cập từ ESP32; kiểm tra lại IP bằng `ip -4 -brief address`.
2. Chạy `sudo systemctl start mariadb`.
3. Mở terminal server, export lại các biến `DB_*` và chạy `python3 tools/run_server.py` như mục 10.
4. Cắm nguồn ESP32, chờ OLED hiện `NHAP MSSV`.
5. Mở dashboard, chọn lớp/bài đã lưu và bấm **Bắt đầu** để tạo phiên mới.
6. Nhập MSSV, chọn đáp án và nhấn `#` để gửi.

Nếu dashboard báo có phiên đang hoạt động, mở lại phiên đó hoặc kết thúc trước khi bắt đầu phiên khác. Dữ liệu lớp, bài kiểm tra và kết quả đã ghi trong MariaDB vẫn được giữ khi tắt máy bình thường.

Để chỉ xem log, trong terminal đã kích hoạt ESP-IDF dùng `idf.py -p /dev/ttyUSB0 monitor`; không cần chạy lệnh flash mỗi lần bật thiết bị.

## 14. Khi đổi Wi-Fi hoặc IP laptop

1. Kết nối laptop vào mạng mới có thể giao tiếp với ESP32.
2. Lấy IPv4 mới của laptop bằng `ip -4 -brief address`.
3. Nếu Wi-Fi đổi tên hoặc mật khẩu, sửa `wifi_connect(...)` trong `main/main.c`.
4. Cập nhật cả `ANSWER_URL` và `STATE_URL` trong `main/http_client.c` bằng IP laptop mới.
5. Lưu file, chạy Flask với cấu hình database hiện tại và kiểm tra truy cập LAN. Nếu dùng quy tắc UFW theo subnet, kiểm tra lại subnet được phép.
6. Chạy `python3 tools/flash_monitor.py` để build/nạp cấu hình mới.
7. Kiểm tra log Wi-Fi, xác nhận MSSV và thử gửi một đáp án.

IP ESP32 có thể thay đổi do DHCP; không cần sửa code vì IP của chính ESP32 thay đổi. Giá trị ghi trong firmware là IP của máy chạy server. Có thể cấu hình DHCP reservation trên router để giữ IP laptop ổn định.

## 15. Tắt bộ thử nghiệm

1. Bấm **Kết thúc phiên** trên dashboard và xác nhận.
2. Nhấn **Ctrl + ]** để thoát serial monitor nếu đang mở.
3. Nhấn **Ctrl + C** trong terminal Flask.
4. Rút USB và ngắt mọi nguồn ngoài cấp cho ESP32.
5. Tắt Ubuntu bình thường nếu không dùng nữa.

ESP32 giữ firmware đã nạp trong flash. MariaDB giữ dữ liệu đã ghi; không cần xóa hoặc import lại database để dừng sử dụng.

## 16. Các script tiện ích

Chạy từ folder `~/IOT`:

| Lệnh | Chức năng |
| --- | --- |
| `python3 tools/run_server.py` | Chạy Flask bằng Python trong `server/venv` |
| `python3 tools/check_backend.py` | Kiểm tra API overview và trạng thái thiết bị |
| `python3 tools/update_server_ip.py` | Ghi cập nhật IP vào hai URL trong `main/http_client.c` |
| `python3 tools/build_esp32.py` | Kích hoạt ESP-IDF và build firmware |
| `python3 tools/flash_monitor.py` | Tìm cổng, build nếu cần, nạp và mở monitor |
| `python3 tools/iot_manager.py` | Mở menu tập hợp các lệnh trên |

Menu số 6 thực hiện **cập nhật IP → build → flash**. Nó không cấu hình Wi-Fi hoặc database và không tự khởi động Flask. Kiểm tra IP tự chọn trước khi dùng với VPN hoặc nhiều interface. Nếu chọn chạy Flask qua menu, terminal đó bị chiếm tới khi dừng server; dùng terminal khác cho build/flash.

## 17. Xử lý lỗi thường gặp

| Hiện tượng | Kiểm tra và xử lý |
| --- | --- |
| `Path '/dev/ttyUSB0' is not readable` / `Permission denied` | Kiểm tra quyền cổng và nhóm `dialout`; đăng xuất/đăng nhập sau khi thêm nhóm hoặc dùng `newgrp dialout`. |
| Không thấy cổng USB serial | Thử rút/cắm, cáp có truyền dữ liệu, cổng USB khác; kiểm tra lại `/dev/ttyUSB*` và `/dev/ttyACM*`. |
| `Connecting...` rồi `No serial data received` | Thử BOOT + EN/RST như mục 11; kiểm tra cáp, nguồn và chương trình khác đang giữ cổng. |
| Không tìm thấy script kích hoạt ESP-IDF | Kiểm tra `~/esp/esp-idf/export.sh` và `ACTIVATE` trong hai script build/flash. |
| `idf.py: command not found` | Chạy `source "$HOME/esp/esp-idf/export.sh"` trong terminal đang dùng. |
| CMake nhắc đường dẫn home của máy khác | Nếu copy project kèm `build`, đổi tên folder build cũ sang tên backup chưa tồn tại rồi build lại. Giữ các file cấu hình của project. |
| `ModuleNotFoundError` cho Flask hoặc MySQL | Tạo lại `server/venv`, cài `server/requirements.txt`, dùng `tools/run_server.py`. |
| `Access denied for user` khi đọc database | Kiểm tra `DB_HOST`, `DB_USER`, `DB_PASSWORD`, tên host của tài khoản MariaDB và quyền trên database. |
| Thiếu bảng `classes`, `quiz_sessions` hoặc cột `active_session_id` | Kiểm tra `DB_NAME`; database mới cần import schema hiện tại. Database cũ cần quy trình migration riêng, không import đè schema lên dữ liệu đang có. |
| OLED dừng ở `KET NOI WIFI...` | Kiểm tra SSID/mật khẩu, Wi-Fi 2.4 GHz và firmware mới đã nạp. |
| OLED `LOI KET NOI` sau xác nhận MSSV | Kiểm tra cả hai URL, Flask đang chạy, firewall, LAN và log HTTP/database trong terminal Flask. |
| `GET /device/state` trả HTTP 500 | Đọc traceback trong terminal Flask, thường cần kiểm tra kết nối hoặc cấu trúc database. |
| OLED `CHUA CO PHIEN` | Đã đọc được trạng thái server; bắt đầu phiên kiểm tra trên dashboard. |
| Chọn A/B/C/D nhưng chưa thấy đáp án trên web | Nhấn thêm `#` để xác nhận gửi. |
| A/B/C/D không hiện ở màn hình nhập MSSV | Đây là hành vi của màn hình nhập số; thử các phím này sau khi vào chế độ trả lời. |
| Bấm một số nhưng hiện số khác, nhiều phím không nhận | Ngắt nguồn; kiểm tra thứ tự hàng/cột keypad, GPIO và đầu dây lỏng. Nếu chưa rõ pinout, đối chiếu model hoặc đo thông mạch khi keypad đã tách khỏi mạch. |
| Không tìm thấy OLED | Kiểm tra module SSD1306 128×32, nguồn/GND, SDA GPIO18, SCL GPIO19 và tiếp xúc dây. |
| Port 5000 đang bị sử dụng | Kiểm tra có Flask đang chạy ở terminal khác không; giữ một tiến trình server cho lần thử này. |

## 18. Cấu trúc repository

```text
main/                          Firmware ESP32
  main.c                       Luồng nhập MSSV và trả lời
  wifi.c                       Kết nối Wi-Fi
  http_client.c                URL và giao tiếp HTTP với Flask
  keypad.c                     Quét keypad và cấu hình GPIO
  oled.c                       Điều khiển OLED
  idf_component.yml            Khai báo thư viện cJSON
server/
  server.py                    Backend hiện tại
  templates/dashboard.html     Dashboard
  requirements.txt             Package Python
  database/schema.sql          Cấu trúc cho database mới
  database/migration_v2.sql     Nâng cấp database phiên bản cũ
tools/                         Script hỗ trợ chạy project
CMakeLists.txt                 Cấu hình build ESP-IDF
sdkconfig.defaults             Cấu hình mặc định của project
dependencies.lock              Khóa phiên bản dependency ESP-IDF
README.md                      Hướng dẫn sử dụng này
```

`build`, `managed_components` và `server/venv` được tạo khi cài/build. `button.c/.h` là phần còn lại trong source, không được đăng ký trong bản build hiện tại. Nếu còn các bản `server_old.py` hoặc `server_backup.py` trong bản copy local, dùng `server/server.py` cho quy trình này.

## 19. Cập nhật README lên GitHub

Sau khi sửa tài liệu, xem lại rồi commit riêng file README:

```bash
cd ~/IOT
git status --short
git diff -- README.md
git add -- README.md
git diff --cached -- README.md
git commit -m "docs: update project setup and usage guide" -- README.md
git push origin main
```

Với file mới chưa được theo dõi, `git diff` trước khi `git add` có thể chưa hiện nội dung; xem bằng editor hoặc dùng bản diff sau khi add. Các lệnh trên dùng nhánh `main`; kiểm tra `git branch --show-current` nếu bạn đang làm việc trên nhánh khác.

Trước khi commit source firmware, kiểm tra không đưa mật khẩu Wi-Fi/database thật lên repository. File SQL dump có dữ liệu sinh viên và virtual environment không cần đưa vào bản source chia sẻ. README chỉ dùng giá trị minh họa; cấu hình thật được điền khi chạy trên máy của người dùng.

## Tài liệu tham khảo

- [Cài ESP-IDF bằng install.sh/export.sh trên Linux](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32/get-started/linux-macos-setup-legacy.html).
- [Chế độ boot và thao tác BOOT/EN của ESP32](https://docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/boot-mode-selection.html).
- [Xử lý lỗi esptool](https://docs.espressif.com/projects/esptool/en/latest/esp32/troubleshooting.html).
- [Đăng nhập GitHub CLI](https://cli.github.com/manual/gh_auth_login).
- [Thêm file local vào repository GitHub](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository).
