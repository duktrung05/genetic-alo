# Timetable Optimization & Benchmarking System (Genetic Algorithm)

Hệ thống tối ưu hóa và xếp lịch thời khóa biểu trường đại học dựa trên **Thuật giải Di truyền (Genetic Algorithm)**, **Heuristic Repair Engine** và tùy chọn **Soft Local Search (SLS)**. Dự án tích hợp bộ so sánh đa phương pháp trên cùng ngân sách đánh giá, hỗ trợ lớp học phần kéo dài nhiều tiết (`duration_periods`) và xuất thời khóa biểu chính thức dưới dạng Excel workbook 7 sheets kèm CSV/JSON metadata.

---

## 📌 Các Tính Năng Nổi Bật

- **Đánh giá Ràng buộc Cứng (Hard Constraints) trên toàn bộ khối tiết (`duration_periods`):**
  - Trùng lịch giảng viên (`lecturer_overlap`): Kiểm tra chồng lặp tiết trên toàn bộ các tiết bị chiếm dụng của giảng viên.
  - Trùng lịch lớp sinh viên (`group_overlap`): Kiểm tra chồng lặp tiết cho từng lớp sinh viên.
  - Trùng phòng học (`room_overlap`): Kiểm tra chồng lặp sử dụng phòng theo tiết.
  - Sức chứa phòng học (`capacity_violation`): Phòng phải đủ sức chứa cho sĩ số lớp.
  - Khung giờ giảng viên rảnh (`lecturer_unavailable`): Giảng viên phải khả dụng trên toàn bộ các tiết của khối lớp.
  - Loại phòng phù hợp (`room_type_mismatch`: NORMAL / LAB): Lớp thực hành (LAB) phải được xếp vào phòng LAB.

- **Đánh giá Ràng buộc Mềm Chuẩn hóa (Soft Constraints S1–S7):**
  - Mỗi objective được chuẩn hóa về `[0, 1]` trước khi nhân stakeholder weight.
  - **S1 `compact_student_schedule` (Balanced weight: 5):** `(total_active_group_days - scheduled_group_count) / (scheduled_group_count × (available_days - 1))`; 0 là compact nhất, 1 là mọi group học trên mọi teaching day.
  - **S2 `late_day_periods` (Weight: 5):** Tỷ lệ tiết học được xếp vào ca tối.
  - **S3 `preferred_shift_mismatch` (Weight: 4):** Tỷ lệ lớp sai ca học mong muốn.
  - **S4 `room_seat_waste` (Balanced weight: 4):** Trung bình tỷ lệ ghế trống theo sức chứa từng phòng.
  - **S5 `consecutive_cross_campus` (Weight: 8):** Tỷ lệ lượt giảng viên chuyển cơ sở giữa hai block liên tiếp.
  - **S6 `preferred_campus_mismatch` (Balanced weight: 3):** Tỷ lệ section sai cơ sở mong muốn.
  - **S7 `student_home_campus_mismatch` (Balanced weight: 4):** Tỷ lệ assignment sai cơ sở chính của nhóm sinh viên.

  > **Weight profiles (S1→S7):** Student-centric `(6,4,5,2,3,3,5)`; **Balanced mặc định** `(5,4,4,4,4,3,4)`; Resource-centric `(3,3,3,10,4,2,3)`. Workbook cũ vẫn load được; production CLI dùng `--weight-profile` để chọn profile rõ ràng. S6 và S7 giữ riêng vì khác business meaning, nhưng current workbook có agreement 62/62 (100%), nên combined weight phải được review để tránh double counting.

- **Dataset Validator (`DatasetValidator`):** Kiểm tra tính hợp lệ và khả thi của dữ liệu trước khi khởi tạo quần thể GA.

- **Heuristic Repair Engine:** Tự động phát hiện và sửa chữa các gen vi phạm cứng sau bước lai ghép/đột biến với chiến lược tìm kiếm ưu tiên 3 tầng (3-tier candidate search).

- **Multi-Seed Benchmark Suite:** So sánh 6 flow độc lập (`repair_only`, `ga`, `ga_repair`, `ga_repair_sls`, `greedy`, `random`) trên cùng ngân sách search evaluations.

- **Xuất thời khóa biểu tự động (Excel Workbook 7 Sheets & Metadata JSON):** Tự động tổng hợp thời khóa biểu tổng quan, theo giảng viên, theo lớp sinh viên, theo phòng học và chi tiết vi phạm.

---

## 📊 Dữ Liệu Đầu Vào (`data/01_data_timetable.xlsx`)

Bộ dữ liệu chuẩn quy mô đại học được nạp từ `data/01_data_timetable.xlsx`:
- **62** lớp học phần (`CourseSection`)
- **15** giảng viên (`Lecturer`)
- **12** nhóm sinh viên (`StudentGroup`)
- **11** phòng học (`Room`: NORMAL & LAB)
- **96** khung giờ tiết học (`Timeslot`: 6 ngày x 16 tiết/ngày, phân ca Sáng / Chiều / Tối)

---

### `CONSTRAINTS` semantics

Soft rows (`S1`–`S7`) provide the effective optimizer weight and enabled flag.
Hard rows are audit declarations only: `HardConstraintChecker` always enforces
all implemented hard checks, their workbook weights do not rescale individual
checks, and `enabled=False` is rejected because disabling a hard check is not
supported in Phase 2.2.

### Multi-meeting scheduling semantics

`CourseSection` remains the official business entity. A section is expanded
deterministically into one `SchedulingActivity` per weekly meeting. Single-
meeting sections retain their section ID as the activity ID; multi-meeting
sections use `SECTION-M1` through `SECTION-MN`. Each activity is assigned its
own room and timeslot, sibling meetings must use distinct teaching days, and
`duration_periods` means the duration of each meeting (not total weekly time).

S1 continues to count unique active days per group. S2, S3, S4, S6, and S7
operate per expanded activity, so their assignment/occupied-period denominators
expand naturally. S5 continues to evaluate adjacent lecturer blocks.

---

## ⏰ Cấu Trúc Khung Giờ Học (HaUI 2025–2026)

Hệ thống tích hợp cấu hình khung giờ học lý thuyết chuẩn Đại học Công nghiệp Hà Nội (HaUI) tại Cơ sở 1 và Cơ sở 2:

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
| **Ca sáng** (`morning`) | Tiết 1 – Tiết 6 | 07:00 – 12:15 |
| **Ca chiều** (`afternoon`) | Tiết 7 – Tiết 12 | 12:30 – 17:45 |
| **Ca tối** (`evening`) | Tiết 13 – Tiết 16 | 18:00 – 21:25 |

---

## ⚙️ Yêu Cầu Môi Trường & Cài Đặt

### Môi Trường
- **OS:** Linux / macOS / Windows
- **Python:** `>= 3.8` (khuyến nghị 3.10+)

### Cài Đặt

```bash
# 1. Tạo và kích hoạt môi trường ảo
python3 -m venv .venv
source .venv/bin/activate  # Trên Windows: .venv\Scripts\activate

# 2. Cài đặt các thư viện phụ thuộc
pip install -r requirements.txt
```

---

## 🧪 Kiểm Thử Hệ Thống (Pytest Suite)

Dự án đi kèm bộ test tự động kiểm tra domain, dataset, constraints, repair engine, GA operators, exporter, production workflow và benchmark metrics. Số lượng test được lấy trực tiếp bằng lệnh collection để tài liệu không bị lệch khi bổ sung regression test.

```bash
# Chạy toàn bộ test suite
pytest -q

# Kiểm tra collection
pytest --collect-only -q
```


---

## Run Demo

```bash
# Activate the project environment, then install dependencies once.
pip install -r requirements.txt

# Start the final Streamlit demo.
streamlit run ui_app.py
```

Open `http://localhost:8501`. The recommended live-demo setup is dataset
**EASY** with the fixed **GA + Repair + SLS** Final Hybrid Method and seed `0`.
The Scheduler page validates the frozen workbook before enabling a run; the
Benchmark page reads the existing Phase 3.1 artifacts and never reruns them.

---

## 🚀 Hướng Dẫn Chạy Hệ Thống

### 1. Tạo Thời Khóa Biểu Production (`main.py`)
Mặc định production sử dụng **GA + Repair**. Có thể bật thêm post-search SLS để tối ưu soft penalty sau khi đã tìm được lịch hard-feasible.

```bash
# Chạy production bằng GA + Repair
python main.py

# Bật thêm Soft Local Search
python main.py --soft-local-search

# Chỉ định input, output, seed và evaluation budget
python main.py --input data/01_data_timetable.xlsx --output outputs/production/best_timetable.xlsx --seed 42
```

### 2. Chạy Benchmark So Sánh Thử Nghiệm (`main_benchmark.py`)
So sánh hiệu năng các phương pháp với cờ `--methods` và số lượng seed tùy chọn:

```bash
# Benchmark production flow và các ablation chính
python main_benchmark.py --methods ga_repair_sls,ga_repair,ga,repair_only,greedy --seeds 0-9 --experiment-name graduation_experiment

# Benchmark nhanh trên mock dataset nhỏ
python main_benchmark.py --methods ga_repair_sls,ga_repair,ga --seeds 0-2 --mode fast --data-source mock --preset small

# Benchmark đầy đủ cả 6 flow
python main_benchmark.py --methods repair_only,ga,ga_repair,ga_repair_sls,greedy,random --seeds 0-9 --experiment-name full_baseline_experiment
```

> **Phân định vai trò phương pháp:**
> - **`ga_repair_sls`:** GA + Repair + SLS, biến thể production đầy đủ.
> - **`ga_repair`:** GA + Repair, cũng là flow mặc định của `main.py` khi không bật SLS.
> - **`ga`:** GA không Repair và không SLS, dùng để đo đóng góp của Repair Engine.
> - **`repair_only`:** Random Restart + Repair, không chạy selection/crossover/mutation.
> - **`greedy`:** Baseline heuristic deterministic, chạy một lần.
> - **`random`:** Baseline lower-bound lấy mẫu ngẫu nhiên.
> - **`hybrid`:** Alias cũ, được tự động chuẩn hóa thành `ga_repair`; không nên dùng trong thí nghiệm mới.
> - *Hệ thống đánh giá các phương pháp bằng feasible rate, hard violations, soft penalty, runtime và thống kê mô tả trên nhiều random seeds.*

### 3. Web Demo — Trợ Lý Tra Cứu Thời Khóa Biểu (`ui_app.py`)
Đây là giao diện Web Demo chỉ đọc (Read-Only Presenter) xây dựng bằng Streamlit. Giao diện **không chạy lại GA, không sửa lịch, không gọi API LLM ngoài và không phụ thuộc Internet**, chỉ đọc dữ liệu production từ JSON/Excel.

```bash
# Khởi chạy Streamlit Web Demo (mặc định cổng 8501)
streamlit run ui_app.py

# Hoặc sử dụng uv:
uv run streamlit run ui_app.py
```
```
docker compose build web-ui
docker compose up -d web-ui
```
Truy cập trình duyệt tại: `http://localhost:8501`

#### Ask Schedule

Trang **Ask Schedule** tra cứu trực tiếp thời khóa biểu vừa được tạo trong phiên Streamlit.
Trợ lý hoạt động offline bằng bộ phân tích ý định deterministic, không cần API/LLM,
và chỉ đọc dữ liệu lịch hiện tại; nó không tạo mới hay thay đổi lịch.

**Ví dụ câu hỏi tra cứu hỗ trợ:**
- `Lịch thứ 2` (Tra cứu tất cả lớp học trong ngày Thứ 2)
- `Lịch của lớp CNTT1` (Tra cứu lịch học của nhóm lớp)
- `Giảng viên GV01 dạy khi nào?` (Tra cứu lịch dạy của giảng viên)
- `Phòng A9-205 được sử dụng khi nào?` (Tra cứu lịch phòng học)
- `Môn Lập trình hướng đối tượng` (Tra cứu lịch học phần môn học)
- `Lịch thứ 2 của lớp CNTT1` (Tra cứu kết hợp nhiều điều kiện)

---

## 📂 Cấu Trúc File Đầu Ra Sau Khi Chạy (`outputs/`)

Toàn bộ dữ liệu kết quả sau khi tối ưu và benchmark được lưu tự động trong thư mục `outputs/`:

```text
outputs/
├── production/
│   ├── best_timetable.xlsx             # Workbook thời khóa biểu chính thức (7 sheets)
│   ├── schedule_query_data.json        # Dữ liệu JSON tra cứu cho Trợ lý tra cứu thời khóa biểu
│   └── convergence_<method>.png        # Ví dụ: convergence_ga_repair_sls.png
├── datasets/
│   └── 01_data_timetable.normalized.json # Snapshot dữ liệu đã chuẩn hóa (fast loader)
└── benchmark/
    └── <experiment_name>/              # Kết quả benchmark thử nghiệm theo tên thí nghiệm
        ├── best_timetable.xlsx         # Workbook thời khóa biểu của phương pháp tốt nhất
        ├── summary.csv                 # Bảng tổng hợp thống kê hiệu năng các phương pháp
        ├── summary.json                # Metadata JSON tổng hợp kết quả
        ├── raw_runs.csv                # Chi tiết dữ liệu từng run/seed
        ├── raw_runs.json               # Chi tiết JSON từng run/seed
        ├── config.json                 # Cấu hình tham số thí nghiệm
        ├── dataset_snapshot.json       # Snapshot dataset thí nghiệm
        ├── convergence_hard.png        # Biểu đồ hội tụ vi phạm cứng
        └── convergence_soft.png        # Biểu đồ hội tụ điểm phạt mềm
```

---

## 📂 Cấu Trúc Thư Mục Dự Án

```text
GA/
├── main.py                        # Entry point production (GA + Repair, optional SLS)
├── main_benchmark.py              # Entry point chạy benchmark so sánh đa phương pháp
├── ui_app.py                      # Giao diện Web UI Trợ lý tra cứu thời khóa biểu (Read-only)
├── README.md                      # Tài liệu hướng dẫn sử dụng và báo cáo dự án
├── pyproject.toml                 # Cấu hình dự án & dependencies
├── requirements.txt               # Danh sách thư viện Python phụ thuộc
├── Dockerfile                     # Cấu hình Docker container
├── docker-compose.yml             # Cấu hình Docker Compose service
├── .gitignore                     # Cấu hình loại trừ Git
│
├── schedule_assistant/            # Package Trợ lý tra cứu (intent_parser, query_service, response_formatter, models)
├── domain/                        # Data models (@dataclass: Schedule, Gene, CourseSection, Room, Timeslot...)
├── dataset/                       # Excel loader, dataset validator, timeslot factory & mock factory
├── constraints/                   # HardConstraintChecker, normalized SoftConstraintChecker (S1-S7) & Repair Engine
├── ga/                            # GeneticAlgorithmEngine & GAOperators (selection, crossover, mutation)
├── evaluation/                    # Baselines (Greedy, Random), metrics, query_data_exporter, visualizer
├── scripts/                       # Script demo chạy GA
├── data/                          # Dữ liệu Excel đầu vào (01_data_timetable.xlsx)
├── outputs/                       # Thư mục chứa kết quả sản phẩm & benchmark
└── tests/                         # Bộ kiểm thử tự động Pytest
```
