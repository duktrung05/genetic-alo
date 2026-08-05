import random
from typing import List, Dict, Optional, FrozenSet
from domain import Course, CourseSection, Room, Lecturer, StudentGroup, Timeslot
from .timeslot_factory import create_theory_timeslots
from .validator import DatasetValidator

def validate_dataset(dataset: dict) -> bool:
    DatasetValidator.validate(dataset)
    return True

class DatasetFactory:
    @staticmethod
    def create_small_dataset() -> dict:
        # 1. 25 Khung giờ (Thứ 2 -> Thứ 6, mỗi ngày 5 tiết)
        days = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6" ,"Thứ 7"]
        timeslots = create_theory_timeslots(
            days=[
                "Thứ 2",
                "Thứ 3",
                "Thứ 4",
                "Thứ 5",
                "Thứ 6",
                "Thứ 7"
            ],
            max_period=16
        )

        # 2. 5 Phòng học (tất cả NORMAL) — campus CS1
        rooms = [
            Room(id="P101", name="Phòng A101", capacity=50, room_type="NORMAL", campus_id="CS1"),
            Room(id="P102", name="Phòng A102", capacity=75, room_type="NORMAL", campus_id="CS1"),
            Room(id="P201", name="Phòng B201", capacity=40, room_type="NORMAL", campus_id="CS1"),
            Room(id="P202", name="Phòng B202", capacity=90, room_type="NORMAL", campus_id="CS1"),
            Room(id="LAB01", name="Phòng Máy Tính 1", capacity=45, room_type="NORMAL", campus_id="CS1"),
        ]

        # 3. 8 Giáo viên (tất cả available = None)
        lecturers = [
            Lecturer(id="GV01", name="ThS. Nguyễn Văn A", available_timeslot_ids=None),
            Lecturer(id="GV02", name="TS. Trần Thị B", available_timeslot_ids=None),
            Lecturer(id="GV03", name="PGS.TS. Lê Văn C", available_timeslot_ids=None),
            Lecturer(id="GV04", name="ThS. Phạm Thị D", available_timeslot_ids=None),
            Lecturer(id="GV05", name="TS. Hoàng Văn E", available_timeslot_ids=None),
            Lecturer(id="GV06", name="ThS. Đỗ Thị F", available_timeslot_ids=None),
            Lecturer(id="GV07", name="TS. Vũ Văn G", available_timeslot_ids=None),
            Lecturer(id="GV08", name="ThS. Bùi Thị H", available_timeslot_ids=None),
        ]

        # 4. 4 Lớp Sinh viên
        student_groups = [
            StudentGroup(id="SV_CNTT1", name="Lớp CNTT01 K18", student_count=65, home_campus_id="CS1"),
            StudentGroup(id="SV_CNTT2", name="Lớp CNTT02 K18", student_count=42, home_campus_id="CS1"),
            StudentGroup(id="SV_KHMT1", name="Lớp KHMT01 K18", student_count=35, home_campus_id="CS1"),
            StudentGroup(id="SV_HTTT1", name="Lớp HTTT01 K18", student_count=80, home_campus_id="CS1"),
        ]

        # 5. Các môn học (Courses)
        courses = [
            Course("CS101", "Cấu trúc dữ liệu & Giải thuật", 3, is_difficult=True),
            Course("CS102", "Lập trình Python nâng cao", 3, is_difficult=False),
            Course("AI201", "Trí tuệ nhân tạo", 3, is_difficult=True),
            Course("DB101", "Cơ sở dữ liệu", 3, is_difficult=True),
            Course("NET101", "Mạng máy tính", 3, is_difficult=False),
            Course("DB201", "Hệ quản trị CSDL", 3, is_difficult=False),
            Course("ML201", "Học máy", 3, is_difficult=True),
            Course("MATH101", "Toán rời rạc", 3, is_difficult=True),
            Course("CG101", "Đồ họa máy tính", 3, is_difficult=False),
            Course("IS101", "Phân tích thiết kế PM", 3, is_difficult=True),
            Course("CO101", "Kiến trúc máy tính", 3, is_difficult=False),
            Course("SEC101", "An toàn thông tin", 3, is_difficult=True),
            Course("WEB101", "Lập trình Web", 3, is_difficult=False),
            Course("IMG101", "Xử lý ảnh số ", 3, is_difficult=False),
        ]

        # 6. Các Lớp Học Phần (CourseSections)
        course_sections = [
            CourseSection("LHP01", "CS101", "Cấu trúc dữ liệu & Giải thuật", "GV01", "SV_CNTT1", 65, is_difficult=True, required_room_type="NORMAL", duration_periods=2),
            CourseSection("LHP02", "CS102", "Lập trình Python nâng cao", "GV02", "SV_CNTT1", 65, is_difficult=False, required_room_type="NORMAL", duration_periods=2),
            CourseSection("LHP03", "AI201", "Trí tuệ nhân tạo", "GV03", "SV_CNTT1", 65, is_difficult=True, required_room_type="NORMAL", duration_periods=2),
            CourseSection("LHP04", "DB101", "Cơ sở dữ liệu", "GV04", "SV_CNTT2", 42, is_difficult=True, required_room_type="NORMAL", duration_periods=1),
            CourseSection("LHP05", "NET101", "Mạng máy tính", "GV05", "SV_CNTT2", 42, is_difficult=False, required_room_type="NORMAL", duration_periods=2),
            CourseSection("LHP06", "DB201", "Hệ quản trị CSDL", "GV04", "SV_CNTT2", 42, is_difficult=False, required_room_type="NORMAL", duration_periods=2),
            CourseSection("LHP07", "ML201", "Thực hành Học máy", "GV03", "SV_KHMT1", 35, is_difficult=True, required_room_type="NORMAL", duration_periods=3),
            CourseSection("LHP08", "MATH101", "Toán rời rạc", "GV06", "SV_KHMT1", 35, is_difficult=True, required_room_type="NORMAL", duration_periods=2),
            CourseSection("LHP09", "CG101", "Đồ họa máy tính", "GV07", "SV_KHMT1", 35, is_difficult=False, required_room_type="NORMAL", duration_periods=1),
            CourseSection("LHP10", "IS101", "Phân tích thiết kế PM", "GV08", "SV_HTTT1", 80, is_difficult=True, required_room_type="NORMAL", duration_periods=2),
            CourseSection("LHP11", "CO101", "Kiến trúc máy tính", "GV05", "SV_HTTT1", 80, is_difficult=False, required_room_type="NORMAL", duration_periods=2),
            CourseSection("LHP12", "SEC101", "An toàn thông tin", "GV01", "SV_HTTT1", 80, is_difficult=True, required_room_type="NORMAL", duration_periods=3),
            CourseSection("LHP13", "WEB101", "Lập trình Web", "GV02", "SV_CNTT2", 42, is_difficult=False, required_room_type="NORMAL", duration_periods=1),
            CourseSection("LHP14", "IMG101", "Xử lý ảnh số ", "GV07", "SV_KHMT1", 35, is_difficult=False, required_room_type="NORMAL", duration_periods=2),
        ]

        ds = {
            "timeslots": timeslots,
            "rooms": rooms,
            "lecturers": lecturers,
            "student_groups": student_groups,
            "courses": courses,
            "course_sections": course_sections,
        }
        validate_dataset(ds)
        return ds

    @staticmethod
    def create_dataset() -> dict:
        return DatasetFactory.create_small_dataset()

    @staticmethod
    def create_medium_dataset(seed: int = 42) -> dict:
        rng = random.Random(seed)

        # 1. 96 Khung giờ (Thứ 2 -> Thứ 7, mỗi ngày 16 tiết)
        days = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7"]
        timeslots = create_theory_timeslots(days=days, max_period=16)
        ts_map: Dict[Tuple[str, int], int] = {(ts.day, ts.period): ts.id for ts in timeslots}

        # 2. 8 Phòng học: 6 phòng NORMAL, 2 phòng LAB; phân bố CS1/CS2 đa dạng
        rooms = [
            Room(id="P101", name="Phòng A101", capacity=40, room_type="NORMAL", campus_id="CS1"),
            Room(id="P102", name="Phòng A102", capacity=50, room_type="NORMAL", campus_id="CS1"),
            Room(id="P103", name="Phòng A103", capacity=65, room_type="NORMAL", campus_id="CS1"),
            Room(id="P201", name="Phòng B201", capacity=80, room_type="NORMAL", campus_id="CS2"),
            Room(id="P202", name="Phòng B202", capacity=100, room_type="NORMAL", campus_id="CS2"),
            Room(id="P301", name="Phòng C301", capacity=120, room_type="NORMAL", campus_id="CS2"),
            Room(id="P302", name="Phòng C302", capacity=100, room_type="LAB", campus_id="CS1"),
            Room(id="LAB01", name="Phòng LAB", capacity=160, room_type="LAB", campus_id="CS2"),
        ]

        # Helper to build contiguous available timeslots for restricted lecturers
        def get_avail_ids(active_days: List[str], periods: range) -> FrozenSet[int]:
            s = set()
            for d in active_days:
                for p in periods:
                    if (d, p) in ts_map:
                        s.add(ts_map[(d, p)])
            return frozenset(s)

        # 3. 15 Giảng viên: 5 người bị giới hạn availability (rảnh 48 slots với block liền tục), 10 người rảnh toàn bộ
        raw_lecturers_info = [
            ("GV01", "ThS. Nguyễn Văn A", get_avail_ids(["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5"], range(1, 13))),
            ("GV02", "TS. Trần Thị B", None),
            ("GV03", "PGS.TS. Lê Văn C", get_avail_ids(["Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6"], range(1, 13))),
            ("GV04", "ThS. Phạm Thị D", None),
            ("GV05", "TS. Hoàng Văn E", get_avail_ids(["Thứ 2", "Thứ 4", "Thứ 6", "Thứ 7"], range(1, 13))),
            ("GV06", "ThS. Đỗ Thị F", None),
            ("GV07", "TS. Vũ Văn G", get_avail_ids(["Thứ 2", "Thứ 3", "Thứ 5", "Thứ 7"], range(5, 17))),
            ("GV08", "ThS. Bùi Thị H", None),
            ("GV09", "TS. Đặng Văn I", get_avail_ids(["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 6"], range(1, 13))),
            ("GV10", "ThS. Ngô Thị K", None),
            ("GV11", "TS. Dương Văn L", None),
            ("GV12", "ThS. Lý Thị M", None),
            ("GV13", "TS. Hồ Văn N", None),
            ("GV14", "ThS. Võ Thị P", None),
            ("GV15", "TS. Trịnh Văn Q", None),
        ]

        lecturers = [Lecturer(id=l_id, name=name, available_timeslot_ids=avail) for l_id, name, avail in raw_lecturers_info]
        lec_ids = [l.id for l in lecturers]

        # 4. 12 Lớp Sinh viên — campus_home phân bố CS1/CS2
        student_groups = [
            StudentGroup(id="SV_CNTT1", name="Lớp CNTT01 K18", student_count=75, home_campus_id="CS1"),
            StudentGroup(id="SV_CNTT2", name="Lớp CNTT02 K18", student_count=65, home_campus_id="CS1"),
            StudentGroup(id="SV_KHMT1", name="Lớp KHMT01 K18", student_count=50, home_campus_id="CS1"),
            StudentGroup(id="SV_HTTT1", name="Lớp HTTT01 K18", student_count=110, home_campus_id="CS1"),
            StudentGroup(id="SV_KTPM1", name="Lớp KTPM01 K18", student_count=45, home_campus_id="CS2"),
            StudentGroup(id="SV_ATTT1", name="Lớp ATTT02 K18", student_count=90, home_campus_id="CS2"),
            StudentGroup(id="SV_CNTT3", name="Lớp CNTT03 K18", student_count=35, home_campus_id="CS2"),
            StudentGroup(id="SV_KHMT2", name="Lớp KHMT02 K18", student_count=100, home_campus_id="CS1"),
            StudentGroup(id="SV_HTTT2", name="Lớp HTTT02 K18", student_count=55, home_campus_id="CS1"),
            StudentGroup(id="SV_KTPM2", name="Lớp KTPM02 K18", student_count=40, home_campus_id="CS2"),
            StudentGroup(id="SV_ATTT2", name="Lớp ATTT02 K18", student_count=70, home_campus_id="CS2"),
            StudentGroup(id="SV_TTNT1", name="Lớp TTNT01 K18", student_count=32, home_campus_id="CS1"),
        ]
        grp_ids = [g.id for g in student_groups]
        group_map = {g.id: g for g in student_groups}

        # 5. 20 Môn học
        courses = [
            Course("CS101", "Cấu trúc dữ liệu & Giải thuật", 3, is_difficult=True),
            Course("CS102", "Lập trình Python nâng cao", 3, is_difficult=False),
            Course("AI201", "Trí tuệ nhân tạo", 3, is_difficult=True),
            Course("DB101", "Cơ sở dữ liệu", 3, is_difficult=True),
            Course("NET101", "Mạng máy tính", 3, is_difficult=False),
            Course("DB201", "Hệ quản trị CSDL", 3, is_difficult=False),
            Course("ML201", "Thực hành Học máy", 3, is_difficult=True),
            Course("MATH101", "Toán rời rạc", 3, is_difficult=True),
            Course("CG101", "Đồ họa máy tính", 3, is_difficult=False),
            Course("IS101", "Phân tích & Thiết kế HT", 3, is_difficult=True),
            Course("CO101", "Kiến trúc máy tính", 3, is_difficult=False),
            Course("SEC101", "An toàn thông tin", 3, is_difficult=True),
            Course("WEB101", "Lập trình Web", 3, is_difficult=False),
            Course("IMG101", "Xử lý ảnh số", 3, is_difficult=False),
            Course("JAVA101", "Lập trình Java", 3, is_difficult=False),
            Course("OS101", "Hệ điều hành", 3, is_difficult=True),
            Course("CLOUD101", "Điện toán đám mây", 3, is_difficult=False),
            Course("SE101", "Kỹ thuật phần mềm", 3, is_difficult=True),
            Course("DM101", "Khai phá dữ liệu", 3, is_difficult=True),
            Course("NLP101", "Xử lý ngôn ngữ tự nhiên", 3, is_difficult=True),
        ]

        # 6. 60 Lớp Học Phần (CourseSections)
        # Distribution: 36 duration 2 (60%), 15 duration 3 (25%), 9 duration 4 (15%)
        # 10 LAB sections (duration 3, required_room_type="LAB")
        lec_assignment = []
        for l in lec_ids:
            lec_assignment.extend([l] * 4)

        grp_assignment = []
        for g in grp_ids:
            grp_assignment.extend([g] * 5)

        durations = [2] * 36 + [3] * 15 + [4] * 9

        # Preference pools for distribution
        _campus_pool = ["CS1"] * 40 + ["CS2"] * 20
        _shift_pool = ["morning"] * 30 + ["afternoon"] * 25 + ["evening"] * 5
        rng.shuffle(_campus_pool)
        rng.shuffle(_shift_pool)

        course_sections: List[CourseSection] = []
        for i in range(60):
            sec_id = f"LHP{i+1:02d}"
            course = courses[i % len(courses)]
            lec_id = lec_assignment[i]
            grp_id = grp_assignment[i]
            st_count = group_map[grp_id].student_count
            is_diff = course.is_difficult
            duration = durations[i]

            if 36 <= i < 46:
                req_room_type = "LAB"
            else:
                req_room_type = "NORMAL"

            course_sections.append(
                CourseSection(
                    section_id=sec_id,
                    course_id=course.course_id,
                    course_name=course.name,
                    lecturer_id=lec_id,
                    group_id=grp_id,
                    student_count=st_count,
                    is_difficult=is_diff,
                    required_room_type=req_room_type,
                    duration_periods=duration,
                    preferred_campus_id=_campus_pool[i],
                    preferred_shift=_shift_pool[i],
                    meetings_per_week=1,
                )
            )

        # Shuffle sections deterministically
        rng.shuffle(course_sections)

        ds = {
            "timeslots": timeslots,
            "rooms": rooms,
            "lecturers": lecturers,
            "student_groups": student_groups,
            "courses": courses,
            "course_sections": course_sections,
        }
        validate_dataset(ds)
        return ds

    @staticmethod
    def create_excel_dataset(excel_path: str = "data/01_data_timetable.xlsx") -> dict:
        """Load and validate dataset from specified Excel workbook path."""
        from .excel_loader import ExcelDatasetLoader
        return ExcelDatasetLoader.load_and_validate(excel_path)


