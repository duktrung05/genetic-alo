# Timetable Optimization & Benchmarking System (Genetic Algorithm)

Hệ thống tối ưu hóa và xếp lịch thời khóa biểu trường đại học dựa trên **Thuật giải Di truyền (Genetic Algorithm)** kết hợp cơ chế sửa lỗi **Heuristic Repair Engine**. Dự án tích hợp bộ so sánh hiệu năng (Benchmark Suite) đa phương pháp trên cùng ngân sách đánh giá (fitness evaluation budget) cho bộ dữ liệu quy mô đại học, hỗ trợ các lớp học phần kéo dài nhiều tiết (`duration_periods`) và xuất thời khóa biểu chính thức dưới dạng Excel workbook 7 sheets (kèm CSV / JSON metadata).

---

## 📌 Các Tính Năng Nổi Bật

- **Đánh giá Ràng buộc Cứng (Hard Constraints) trên toàn bộ khối tiết (`duration_periods`):**
  - Trùng lịch giảng viên (`lecturer_overlap`): Kiểm tra chồng lặp tiết trên toàn bộ các tiết bị chiếm dụng của giảng viên.
  - Trùng lịch lớp sinh viên (`group_overlap`): Kiểm tra chồng lặp tiết cho từng lớp sinh viên.
  - Trùng phòng học (`room_overlap`): Kiểm tra chồng lặp sử dụng phòng theo tiết.
  - Sức chứa phòng học (`capacity_violation`): Phòng phải đủ sức chứa cho sĩ số lớp.
  - Khung giờ giảng viên rảnh (`lecturer_unavailable`): Giảng viên phải khả dụng trên toàn bộ các tiết của khối lớp.
  - Loại phòng phù hợp (`room_type_mismatch`: NORMAL / LAB): Lớp thực hành (LAB) phải được xếp vào phòng LAB.

- **Đánh giá Ràng buộc Mềm có Trọng số (Excel-driven Soft Constraints S1–S5):**
  - **S1 `weekly_distribution` (Weight: 10):** Phân bố môn học của mỗi nhóm sinh viên đều trong tuần.
  - **S2 `late_day_periods` (Weight: 5):** Hạn chế quá nhiều tiết học vào ca tối (ca `evening`).
  - **S3 `preferred_shift_mismatch` (Weight: 4):** Ưu tiên xếp lớp học phần đúng ca học mong muốn (`preferred_shift`).
  - **S4 `room_seat_waste` (Weight: 2):** Giảm số ghế trống lãng phí trong phòng học.
  - **S5 `consecutive_cross_campus` (Weight: 8):** Hạn chế giảng viên di chuyển liên tiếp giữa 2 cơ sở trong ngày.
  
  > *Lưu ý:* Trọng số và trạng thái `enabled` của S1–S5 được tự động đọc trực tiếp từ sheet `CONSTRAINTS` của file Excel đầu vào (`data/01_data_timetable.xlsx`).

- **Dataset Validator (`DatasetValidator`):** Kiểm tra tính hợp lệ và khả thi của dữ liệu trước khi khởi tạo quần thể GA.

- **Heuristic Repair Engine:** Tự động phát hiện và sửa chữa các gen vi phạm cứng sau bước lai ghép/đột biến với chiến lược tìm kiếm ưu tiên 3 tầng (3-tier candidate search).

- **Multi-Seed Benchmark Suite:** So sánh 4 phương pháp (`Hybrid GA + Repair`, `GA without Repair`, `Greedy Search`, `Random Search`) trên cùng ngân sách evaluations với cờ `--methods` tùy chọn.

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

Dự án đi kèm bộ test tự động toàn diện: **`309 tests passed / 0 failed`** (bao gồm 10 unit tests thử nghiệm Soft-Guided Mutation và 18 unit tests cho Soft Local Search), kiểm thử toàn bộ domain, dataset, constraints, repair engine, GA operators, exporter và benchmark metrics.

```bash
# Chạy toàn bộ 309 test cases
pytest -q

# Kiểm tra collection
pytest --collect-only -q
```


---

## 🚀 Hướng Dẫn Chạy Hệ Thống

### 1. Tạo Thời Khóa Biểu Production (`main.py`)
Sử dụng phương pháp đề xuất chính **Hybrid GA + Repair** để tạo thời khóa biểu chính thức:

```bash
# Chạy tạo thời khóa biểu sản phẩm bằng Hybrid GA + Repair
python main.py

# Chỉ định file Excel đầu vào và đường dẫn xuất workbook:
python main.py --input data/01_data_timetable.xlsx --output outputs/production/best_timetable.xlsx --seed 42
```

### 2. Chạy Benchmark So Sánh Thử Nghiệm (`main_benchmark.py`)
So sánh hiệu năng các phương pháp với cờ `--methods` và số lượng seed tùy chọn:

```bash
# Benchmark chính thức phục vụ đồ án (Hybrid, Ablation GA, Greedy Baseline):
python main_benchmark.py --methods hybrid,ga,greedy --seeds 0-9 --experiment-name graduation_experiment

# Benchmark thử nghiệm nhanh (chế độ Fast):
python main_benchmark.py --methods hybrid,ga,greedy --seeds 0-2 --mode fast

# Benchmark mở rộng toàn bộ phương pháp (bao gồm Random Search):
python main_benchmark.py --methods hybrid,ga,greedy,random --seeds 0-9 --experiment-name full_baseline_experiment
```

> **Phân định vai trò phương pháp:**
> - **`hybrid` (Hybrid GA + Repair):** Phương pháp đề xuất chính duy nhất dùng trong production (`main.py`).
> - **`ga` (GA without Repair):** Thuật toán GA tiêu chuẩn dùng làm thí nghiệm Ablation Study nhằm chứng minh đóng góp của Repair Engine.
> - **`greedy` (Greedy Search):** Baseline Heuristic định hướng (deterministic), không tham gia vào luồng sản phẩm của Hybrid GA.
> - **`random` (Random Search):** Baseline Lower Bound lấy mẫu ngẫu nhiên (chỉ dùng cho benchmark đánh giá).
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
│   └── convergence_hybrid.png          # Biểu đồ hội tụ vi phạm cứng & mềm của Hybrid GA
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
├── main.py                        # Entry point tạo thời khóa biểu sản phẩm (Hybrid GA + Repair)
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
├── constraints/                   # HardConstraintChecker, SoftConstraintChecker (S1-S5) & ScheduleRepairEngine
├── ga/                            # GeneticAlgorithmEngine & GAOperators (selection, crossover, mutation)
├── evaluation/                    # Baselines (Greedy, Random), metrics, query_data_exporter, visualizer
├── docs/                          # Tài liệu kỹ thuật ERD schema & phân tích thuật toán
├── scripts/                       # Script demo chạy GA
├── data/                          # Dữ liệu Excel đầu vào (01_data_timetable.xlsx)
├── outputs/                       # Thư mục chứa kết quả sản phẩm & benchmark
└── tests/                         # Bộ kiểm thử tự động Pytest
```
