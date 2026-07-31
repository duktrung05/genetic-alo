# Timetable Optimization & Benchmarking System (Genetic Algorithm)

Hệ thống tối ưu hóa và xếp lịch thời khóa biểu trường đại học dựa trên **Thuật giải Di truyền (Genetic Algorithm)** kết hợp với cơ chế sửa lỗi **Heuristic Repair Engine**. Dự án tích hợp bộ so sánh hiệu năng (Benchmark Suite) đa phương pháp với cùng ngân sách đánh giá (fitness evaluation budget) trên bộ dữ liệu quy mô đại học, hỗ trợ các lớp học phần kéo dài nhiều tiết (`duration_periods`) và xuất thời khóa biểu hợp lệ ra file CSV theo khung giờ thực tế.

---

## 📌 Các Tính Năng Nổi Bật

- **Đánh giá Ràng buộc Cứng (Hard Constraints) trên toàn bộ khối tiết (`duration_periods`):**
  - Trùng lịch giảng viên (`lecturer_overlap`): Kiểm tra chồng lặp tiết trên toàn bộ các tiết bị chiếm dụng của giảng viên.
  - Trùng lịch lớp sinh viên (`group_overlap`): Kiểm tra chồng lặp tiết cho từng lớp sinh viên.
  - Trùng phòng học (`room_overlap`): Kiểm tra chồng lặp sử dụng phòng theo tiết.
  - Sức chứa phòng học (`capacity_violation`): Phòng phải đủ sức chứa cho sĩ số lớp.
  - Khung giờ giảng viên rảnh (`lecturer_unavailable`): Giảng viên phải khả dụng trên toàn bộ các tiết của khối lớp.
  - Loại phòng phù hợp (`room_type_mismatch`: NORMAL / LAB): Lớp thực hành (LAB) phải được xếp vào phòng LAB.

- **Đánh giá Ràng buộc Mềm có Trọng số (Weighted Soft Constraints):**
  - Hạn chế khoảng trống lịch học của sinh viên (`student_gaps`): Tính theo khoảng tiết trống thực tế giữa các khối tiết trong ngày (lớp 2-3 tiết liên tiếp không bị tính nhầm tiết trống).
  - Giảm thiểu số tiết dạy liên tục của giảng viên (`consecutive_teaching`): Tính tổng số tiết dạy liên tiếp thực tế trong ngày.
  - Hạn chế xếp môn khó vào ca chiều/tối (`difficult_afternoon`).
  - Phân bổ đều tải học theo ngày (`daily_imbalance`): Tính tổng số tiết học thực tế trong ngày của sinh viên.

- **Dataset Validator (`DatasetValidator`):** Tự động kiểm tra tính hợp lệ và khả thi của dữ liệu (trùng ID, lỗi khóa ngoại, thời lượng < 1, thiếu phòng LAB, giảng viên không có khối tiết rảnh) trước khi khởi tạo quần thể GA.

- **Heuristic Repair Engine:** Tự động phát hiện và sửa chữa các gen vi phạm cứng sau bước lai ghép/đột biến, đảm bảo khối tiết liên tiếp không vượt ca (sáng/chiều/tối).

- **Multi-Seed Benchmark Suite:** So sánh 4 phương pháp (`GA without Repair`, `Hybrid GA + Repair`, `Greedy Search`, `Random Search`) trên cùng ngân sách evaluations với nhiều random seed.

- **Xuất thời khóa biểu tự động (CSV chuẩn 13 cột & Metadata JSON):** Chọn thời khóa biểu tốt nhất của Hybrid GA và xuất ra file CSV với đầy đủ thông tin tiết bắt đầu/kết thúc, giờ học thực tế và ca học.

---

## ⏰ Cấu Trúc Khung Giờ Học (HaUI 2025–2026)

Hệ thống tích hợp cấu hình khung giờ học lý thuyết chuẩn Đại học Công nghiệp Hà Nội (HaUI) năm học 2025–2026 tại Cơ sở 1 và Cơ sở 2:

### Model `Timeslot`
```python
@dataclass(frozen=True)
class Timeslot:
    id: int            # Mã khung giờ (0, 1, 2, ...)
    day: str           # Ngày trong tuần ("Thứ 2", "Thứ 3", ..., "Thứ 7")
    period: int        # Tiết học (1 đến 16)
    start_time: str    # Giờ bắt đầu (VD: "07:00", "07:50")
    end_time: str      # Giờ kết thúc (VD: "07:50", "08:40")
    session: str       # Ca học: "morning", "afternoon", "evening"
```

### Bảng Khung Giờ Tiết Học
| Ca học (`session`) | Tiết (`period`) | Thời gian thực tế (`start_time` – `end_time`) |
| :--- | :--- | :--- |
| **Ca sáng** (`morning`) | Tiết 1 | 07:00 – 07:50 |
| | Tiết 2 | 07:50 – 08:40 |
| | Tiết 3 | 08:45 – 09:35 |
| | Tiết 4 | 09:40 – 10:30 |
| | Tiết 5 | 10:35 – 11:25 |
| | Tiết 6 | 11:25 – 12:15 |
| **Ca chiều** (`afternoon`) | Tiết 7 | 12:30 – 13:20 |
| | Tiết 8 | 13:20 – 14:10 |
| | Tiết 9 | 14:15 – 15:05 |
| | Tiết 10 | 15:10 – 16:00 |
| | Tiết 11 | 16:05 – 16:55 |
| | Tiết 12 | 16:55 – 17:45 |
| **Ca tối** (`evening`) | Tiết 13 | 18:00 – 18:50 |
| | Tiết 14 | 18:50 – 19:40 |
| | Tiết 15 | 19:45 – 20:35 |
| | Tiết 16 | 20:35 – 21:25 |

---

## ⏱️ Ý Nghĩa `duration_periods` & `Gene.timeslot_id`

- **`CourseSection.duration_periods`:** Số tiết liên tiếp mà một lớp học phần chiếm dụng ($1, 2, 3, \dots$).
  - **Lớp lý thuyết:** Thường có `duration_periods = 2` (60% dữ liệu) hoặc `duration_periods = 1` (20% dữ liệu).
  - **Lớp thực hành (LAB):** Có `duration_periods = 3` và yêu cầu `required_room_type = "LAB"` (20% dữ liệu).
- **`Gene.timeslot_id`:** Lưu ID của khung giờ **bắt đầu** (`start_timeslot`).
- **Quy tắc nguyên khối theo ca (`is_valid_period_block`):**
  Tất cả các tiết thuộc khối $\text{occupied\_periods} = [\text{start\_period}, \dots, \text{start\_period} + \text{duration} - 1]$ phải nằm gọn hoàn toàn trong **cùng một ca học** (không vắt từ Ca sáng sang Ca chiều hay Ca chiều sang Ca tối).

### 💡 Ví dụ Lớp 3 tiết Thực hành
Giả sử Lớp học phần `LHP07` (Thực hành Học máy) có:
- `duration_periods = 3`
- `required_room_type = "LAB"`
- Gen gán `timeslot_id = 1` (Thứ 2, Tiết 2, Ca sáng)
- **Tải tiết chiếm dụng:** Tiết 2, Tiết 3, Tiết 4 (`occupied_periods = [2, 3, 4]`).
- **Thời gian thực tế:** Bắt đầu lúc `07:50` (bắt đầu Tiết 2), kết thúc lúc `10:30` (kết thúc Tiết 4).
- **Phòng học:** `LAB01` (loại phòng `LAB`, sức chứa $\ge$ sĩ số sinh viên).

---

## ⚙️ Yêu Cầu Môi Trường & Cài Đặt

### Môi Trường
- **OS:** Windows / Linux / macOS
- **Python:** `>= 3.8` (khuyến nghị 3.10+)

### Cài Đặt

#### Trên Windows (PowerShell / CMD):
```powershell
# 1. Tạo môi trường ảo
python -m venv .venv

# 2. Kích hoạt môi trường ảo
# Trong PowerShell:
.\.venv\Scripts\Activate.ps1
# Hoặc trong CMD (Command Prompt):
.\.venv\Scripts\activate.bat

# 3. Cài đặt các thư viện phụ thuộc
pip install -r requirements.txt
```

#### Trên Linux / macOS:
```bash
# 1. Tạo môi trường ảo
python3 -m venv .venv

# 2. Kích hoạt môi trường ảo
source .venv/bin/activate

# 3. Cài đặt các thư viện phụ thuộc
pip install -r requirements.txt
```

---

## 🧪 Hướng Dẫn Chạy Tests

Dự án đi kèm bộ unit tests toàn diện (**152 test cases**) kiểm thử toàn bộ ràng buộc cứng, mềm, toán tử GA, repair engine và exporter.

Chạy toàn bộ tests:
```bash
pytest -v
```

---

## 📊 Hướng Dẫn Chạy Benchmark & Test Suite

### 1. Chạy Bộ Kiểm Thử (Pytest Suite)
```bash
# Chạy toàn bộ test suite
pytest -v

# Chạy nhanh các test đơn vị (Unit Tests)
pytest -m unit -v

# Chạy các test tích hợp (Integration Tests)
pytest -m integration -v
```

### 2. Chạy Demo & Benchmark So Sánh

```bash
# 1. Chạy Demo tối ưu GA & xuất trực tiếp file Thời khóa biểu (Excel & CSV):
python scripts/run_ga_demo.py
# Hoặc chạy qua Docker:
docker compose up --build test-ga

# 2. Chạy Benchmark đầy đủ & xuất Báo cáo (Excel, CSV, Charts & JSON):
python main_benchmark.py --mode report
# Hoặc chạy qua Docker:
docker compose up --build benchmark
```

---

## 📂 Cấu Trúc File Đầu Ra Sau Khi Chạy (`outputs/`)

Toàn bộ dữ liệu kết quả sau khi tối ưu và benchmark được lưu tự động trong thư mục `outputs/`:

```text
outputs/
├── timetables/
│   ├── best_timetable.csv             # Thời khóa biểu tối ưu tốt nhất (13 cột chuẩn)
│   └── best_timetable_metadata.json   # Thông số metadata của kết quả tối ưu
├── benchmarks/
│   └── benchmark_results_multiseed.json # Chi tiết kết quả benchmark multi-seed 4 phương pháp
└── charts/
    ├── convergence_hard.png            # Biểu đồ hội tụ vi phạm cứng
    └── convergence_soft.png            # Biểu đồ hội tụ điểm phạt mềm
```

---

## 📋 Cấu Trúc File CSV Thời Khóa Biểu (`13 Cột`)

File thời khóa biểu tốt nhất được lưu tại: [outputs/timetables/best_timetable.csv](file:///home/trung.nguyen12/Downloads/GA/outputs/timetables/best_timetable.csv).

| Cột CSV | Ý nghĩa | Ví dụ |
| :--- | :--- | :--- |
| `section_id` | Mã lớp học phần | `LHP01` |
| `course_id` | Mã môn học | `CS101` |
| `lecturer_id` | Mã giảng viên | `GV01` |
| `student_group_id` | Mã lớp sinh viên | `SV_CNTT1` |
| `room_id` | Mã phòng học | `P101` |
| `day` | Ngày học trong tuần | `Thứ 2` |
| `start_period` | Tiết bắt đầu | `1` |
| `end_period` | Tiết kết thúc | `2` |
| `start_time` | Giờ bắt đầu | `07:00` |
| `end_time` | Giờ kết thúc | `08:40` |
| `duration_periods` | Số tiết của lớp | `2` |
| `session` | Ca học | `morning` |
| `room_type` | Loại phòng học | `NORMAL` |

### 📝 Ví Dụ Dữ Liệu File CSV Output
```csv
section_id,course_id,lecturer_id,student_group_id,room_id,day,start_period,end_period,start_time,end_time,duration_periods,session,room_type
LHP01,CS101,GV01,SV_CNTT1,P101,Thứ 2,1,2,07:00,08:40,2,morning,NORMAL
LHP07,ML201,GV03,SV_KHMT1,LAB01,Thứ 2,2,4,07:50,10:30,3,morning,LAB
LHP04,DB101,GV04,SV_CNTT2,P102,Thứ 2,5,5,10:35,11:25,1,morning,NORMAL
LHP05,NET101,GV05,SV_CNTT2,P201,Thứ 3,7,8,12:30,14:10,2,afternoon,NORMAL
```

---

## 📂 Cấu Trúc Thư Mục Dự Án

```text
constraints/     HardConstraints, SoftConstraints và ScheduleRepairEngine
dataset/         DatasetFactory, DatasetValidator và timeslot_factory (HaUI periods)
domain/          Course, CourseSection, Lecturer, Room, StudentGroup, Timeslot, Schedule, Gene
ga/              GeneticAlgorithmEngine (Genetic Algorithm with Constraint Repair), GAOperators
evaluation/      Baselines, metrics, benchmark_statistics, visualizer, schedule_exporter
scripts/         run_ga_demo.py (Script demo chạy GA xếp thời khóa biểu)
outputs/         Thư mục chứa kết quả CSV, JSON metadata, benchmark JSON và biểu đồ PNG
tests/           Automated pytest suite (7 files tiêu chuẩn)
main_benchmark.py Benchmark chính so sánh 4 thuật toán & xuất thời khóa biểu
```
