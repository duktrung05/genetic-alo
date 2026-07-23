# Timetable Optimization & Benchmarking System (Genetic Algorithm)

Hệ thống tối ưu hóa và xếp lịch thời khóa biểu trường đại học dựa trên **Thuật giải Di truyền (Genetic Algorithm)** kết hợp với cơ chế sửa lỗi **Heuristic Repair Engine**. Dự án tích hợp bộ so sánh hiệu năng (Benchmark Suite) đa phương pháp với cùng ngân sách đánh giá (fitness evaluation budget) trên bộ dữ liệu quy mô đại học, hỗ trợ xuất thời khóa biểu hợp lệ ra file CSV.

---

## 📌 Các Tính Năng Nổi Bật

- **Đánh giá Ràng buộc Cứng (Hard Constraints):**
  - Trùng lịch giảng viên (`lecturer_overlap`)
  - Trùng lịch lớp sinh viên (`group_overlap`)
  - Trùng phòng học (`room_overlap`)
  - Sức chứa phòng học (`capacity_violation`)
  - Khung giờ giảng viên rảnh (`lecturer_unavailable`)
  - Loại phòng phù hợp (`room_type_mismatch`: NORMAL / LAB)

- **Đánh giá Ràng buộc Mềm có Trọng số (Weighted Soft Constraints):**
  - Hạn chế khoảng trống lịch học của sinh viên (`student_gaps`)
  - Giảm thiểu số tiết dạy liên tục của giảng viên (`consecutive_teaching`)
  - Hạn chế xếp môn khó vào ca chiều (`difficult_afternoon`)
  - Phân bổ đều tải học theo ngày (`daily_imbalance`)

- **Heuristic Repair Engine:** Tự động phát hiện và sửa chữa các gen vi phạm cứng sau bước lai ghép/đột biến, giúp GA hội tụ về nghiệm hợp lệ (0 vi phạm cứng).

- **Multi-Seed Benchmark Suite:** So sánh 4 phương pháp (`GA without Repair`, `Hybrid GA + Repair`, `Greedy Search`, `Random Search`) trên cùng ngân sách 6000 evaluations với 30 random seed.

- **Xuất thời khóa biểu tự động (CSV & Metadata JSON):** Chọn thời khóa biểu tốt nhất của Hybrid GA theo thứ tự ưu tiên lexicographic `(hard_violations, soft_penalty)` và xuất ra file CSV (chuẩn UTF-8 với BOM `utf-8-sig`).

---

## ⚙️ Yêu Cầu Môi Trường

Hệ thống được phát triển và kiểm thử trên môi trường **Ubuntu / Linux**:

- **Python:** `>= 3.8` (khuyến nghị Python 3.10 hoặc 3.11)
- **Pip & Venv:** Đã cài `python3-venv` và `python3-pip`
- **Docker & Docker Compose:** (Tùy chọn nếu muốn chạy bằng container)

---

## 🚀 Cài Đặt & Chạy Trực Tiếp

Thực hiện các lệnh sau từ thư mục root của repository:

```bash
# 1. Tạo môi trường ảo
python3 -m venv .venv

# 2. Kích hoạt môi trường ảo (Linux / Ubuntu)
source .venv/bin/activate

# 3. Nâng cấp pip
python -m pip install --upgrade pip

# 4. Cài đặt các thư viện phụ thuộc
pip install -r requirements.txt
```
*(Có thể dùng `pip install -e .` để cài đặt dự án dưới dạng editable package).*

---

## 🧪 Hướng Dẫn Chạy Tests

Dự án đi kèm bộ unit tests toàn diện (83 test cases) nằm trong thư mục `tests/`.

Chạy toàn bộ tests:

```bash
pytest -q
```

---

## 📊 Hướng Dẫn Chạy Benchmark Trực Tiếp

Chạy file benchmark chính:

```bash
python main_benchmark.py
```

> **Ghi chú:** Tiến trình benchmark đầy đủ sử dụng bộ dữ liệu **MEDIUM** (60 Lớp học phần, 15 Giảng viên, 8 Phòng học, 12 Lớp sinh viên, 30 Khung giờ), thực hiện **30 seed** với ngân sách **6000 fitness evaluations/seed**. Quá trình chạy có thể mất vài phút tùy theo cấu hình phần cứng của máy.

---

## 🐳 Chạy Bằng Docker

Cấu hình Docker Compose trong `docker-compose.yml` cung cấp hai service chính là `benchmark` và `test-ga`.

### 1. Chạy Benchmark Bằng Docker Compose (Khuyến nghị)

```bash
docker compose up --build benchmark
libreoffice --calc evaluation/exports/best_timetable.csv
```

- Cờ `--build` đảm bảo Docker tự động rebuild image mới nhất.
- Kết quả chạy benchmark sẽ hiển thị trực tiếp trên terminal.
- Do thư mục `./evaluation` đã được mount volume sang `/app/evaluation` trong container, tất cả file kết quả sẽ được lưu trực tiếp trên máy host tại thư mục:
  `evaluation/` và `evaluation/exports/`.

### 2. Chạy Tests Bằng Docker Compose

```bash
docker compose up --build test-ga
```

### 3. Build & Chạy Trực Tiếp Bằng Docker CLI

```bash
# Build Docker image
docker build -t ga-timetabling .

# Chạy container benchmark và lưu kết quả ra máy host
docker run --rm -v $(pwd)/evaluation:/app/evaluation ga-timetabling
```

---

## 📁 Kết Quả Đầu Ra

Sau khi hoàn thành benchmark, các file kết quả sau sẽ được tự động sinh ra trong thư mục `evaluation/`:

- `evaluation/benchmark_results_multiseed.json`: Kết quả chi tiết 30 seed và thống kê tổng hợp của 4 phương pháp.
- `evaluation/convergence_hard.png`: Biểu đồ so sánh số vi phạm cứng (hard violations) tốt nhất theo số lần đánh giá fitness.
- `evaluation/convergence_soft.png`: Biểu đồ so sánh điểm phạt mềm (soft penalty) tốt nhất theo số lần đánh giá fitness.
- `evaluation/exports/best_timetable.csv`: File thời khóa biểu tốt nhất của thuật toán `Hybrid GA + Repair`.
- `evaluation/exports/best_timetable_metadata.json`: File lưu thông tin seed, metrics và cấu hình dữ liệu liên quan tới thời khóa biểu đã xuất.

---

## 📅 Cách Mở File Thời Khóa Biểu CSV

File thời khóa biểu tốt nhất được lưu tại: [evaluation/exports/best_timetable.csv](file:///home/trung.nguyen12/Downloads/GA/evaluation/exports/best_timetable.csv).

### 1. Mở Trong VS Code
Cài đặt extension **Rainbow CSV** hoặc **CSV Editor** để xem dữ liệu dạng bảng có màu phân biệt trực tiếp trong VS Code.

### 2. Mở Bằng LibreOffice Calc (Ubuntu / Linux)

Cài đặt LibreOffice Calc (nếu chưa có):

```bash
sudo apt update
sudo apt install libreoffice-calc
```

Mở file từ terminal:

```bash
libreoffice --calc evaluation/exports/best_timetable.csv
```

Khi hộp thoại **Text Import** xuất hiện, chọn các thiết lập sau:
- **Character set:** `Unicode (UTF-8)`
- **Separated by:** Chọn mục này
- **Dấu phân cách:** Chỉ chọn **Comma (dấu phẩy)**. BỎ chọn *Tab*, *Semicolon* và *Space*.
- Nhấn **OK**.

> **Lưu ý khi muốn chuyển sang Excel:** Trong LibreOffice Calc, chọn `File` -> `Save As...` -> Chọn định dạng `Excel 2007–365 (.xlsx)`. File gốc sinh ra là định dạng CSV, không phải XLSX.

---

## 📋 Cấu Trúc File CSV

File CSV bao gồm 17 cột dữ liệu (mỗi dòng tương ứng với đúng 1 Lớp học phần):

1. `Day`: Thứ trong tuần (Thứ 2 -> Thứ 6)
2. `Period`: Tiết học (1 -> 6)
3. `Timeslot ID`: Mã số khung giờ (0 -> 29)
4. `Section ID`: Mã lớp học phần (ví dụ: LHP01)
5. `Course ID`: Mã môn học (ví dụ: CS101)
6. `Course Name`: Tên môn học
7. `Lecturer ID`: Mã giảng viên (ví dụ: GV01)
8. `Lecturer Name`: Họ tên giảng viên
9. `Student Group ID`: Mã lớp sinh viên (ví dụ: SV_CNTT1)
10. `Student Group Name`: Tên lớp sinh viên
11. `Student Count`: Sĩ số sinh viên
12. `Room ID`: Mã phòng học (ví dụ: P101, LAB01)
13. `Room Name`: Tên phòng học
14. `Room Capacity`: Sức chứa phòng học
15. `Room Type`: Loại phòng (`NORMAL` / `LAB`)
16. `Required Room Type`: Loại phòng yêu cầu (`NORMAL` / `LAB`)
17. `Is Difficult`: Môn học khó (`True` / `False`)

---

## 📈 Cách Đọc Kết Quả Benchmark

- **Hard Violations = 0:** Thời khóa biểu hợp lệ (thỏa mãn tất cả 6 ràng buộc cứng).
- **Raw Soft Violations:** Số lượng vi phạm ràng buộc mềm thô.
- **Soft Penalty:** Tổng điểm phạt vi phạm mềm sau khi nhân với trọng số.
- **Thứ Tự Ưu Tiên Lexicographic Fitness:** Thuật toán luôn ưu tiên giảm `Hard Violations` trước. Nếu số vi phạm cứng bằng nhau, mới xét giảm `Soft Penalty`.
- **Feasible Rate (%):** Tỷ lệ số lượt chạy tìm được lịch hợp lệ (Hard Violations = 0).
- **Perfect Rate (%):** Tỷ lệ số lượt chạy tìm được lịch hoàn hảo (Hard Violations = 0 và Soft Penalty = 0).
- **Fitness Evaluations:** Tổng số lần đánh giá phương án (được cố định 6000 evaluations/seed để so sánh công bằng).

---

## 📂 Cấu Trúc Thư Mục Ngắn Gọn

```text
constraints/     Hard, soft constraints và repair engine
dataset/         Small và medium dataset factories
domain/          Các entity của bài toán (Course, Lecturer, Room, Schedule, ...)
ga/              Genetic Algorithm engine và operators
evaluation/      Baselines, metrics, statistics, visualizer, exporter
tests/           Automated unit tests (83 test cases)
main_benchmark.py Benchmark chính so sánh 4 thuật toán & xuất lịch tốt nhất
```

---

## 🛠️ Troubleshooting (Xử Lý Lỗi Thường Gặp)

- **`python: command not found`:**
  Sử dụng lệnh `python3` hoặc đảm bảo đã kích hoạt môi trường ảo (`source .venv/bin/activate`).

- **`pytest: command not found`:**
  Chưa cài thư viện hoặc chưa kích hoạt `.venv`. Chạy `pip install -r requirements.txt` hoặc kiểm tra môi trường ảo.

- **`libreoffice: command not found`:**
  Cài đặt ứng dụng bằng lệnh: `sudo apt install libreoffice-calc`.

- **Cảnh báo `Warning: failed to launch javaldx` khi mở LibreOffice:**
  Đây là cảnh báo Java của LibreOffice. Cảnh báo này **không ảnh hưởng** đến việc đọc file CSV và có thể an tâm bỏ qua nếu phần mềm vẫn mở được bảng tính.

- **Dữ liệu CSV bị dồn hết vào một cột:**
  Trong hộp thoại *Text Import* của LibreOffice Calc, chọn **Separated by** và chỉ đánh dấu chọn duy nhất ô **Comma (dấu phẩy)**.

- **Không thấy file export:**
  Kiểm tra thư mục bằng lệnh `ls -lh evaluation/exports/` và đảm bảo lệnh `python main_benchmark.py` đã chạy xong hoàn toàn.
