import os
import json
from pathlib import Path
import pandas as pd
import streamlit as st

from schedule_assistant import ScheduleQueryService, ResponseFormatter, IntentParser


# Page Configuration
st.set_page_config(
    page_title="Hệ thống xếp thời khóa biểu tự động — Streamlit Web UI",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Canonical Day Order for deterministic sorting
DAY_ORDER = {
    "Thứ 2": 1, "Monday": 1,
    "Thứ 3": 2, "Tuesday": 2,
    "Thứ 4": 3, "Wednesday": 3,
    "Thứ 5": 4, "Thursday": 4,
    "Thứ 6": 5, "Friday": 5,
    "Thứ 7": 6, "Saturday": 6,
    "Chủ nhật": 7, "Sunday": 7,
}


@st.cache_resource
def get_query_service(json_path: str):
    return ScheduleQueryService(data_path=json_path)


def load_production_data():
    json_path = Path("outputs/production/schedule_query_data.json")
    meta_path = Path("outputs/production/best_timetable_metadata.json")

    if not json_path.exists():
        return None, None

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            query_data = json.load(f)

        meta = {}
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        else:
            meta = query_data.get("meta", {})

        return query_data, meta
    except Exception:
        return None, None


def sort_assignments(assignments: list) -> list:
    return sorted(
        assignments,
        key=lambda a: (
            DAY_ORDER.get(a.get("day", ""), 99),
            a.get("start_period", 1),
            a.get("room_name", ""),
            a.get("section_id", ""),
        )
    )


def format_dataframe(assignments: list) -> pd.DataFrame:
    """Format list of assignment dicts into pandas DataFrame matching required column titles."""
    rows = []
    for a in sort_assignments(assignments):
        start_p = a.get("start_period", 1)
        end_p = a.get("end_period", 1)
        p_str = f"Tiết {start_p}" if start_p == end_p else f"Tiết {start_p}–{end_p}"
        start_t = a.get("start_time", "")
        end_t = a.get("end_time", "")
        time_str = f"{start_t} – {end_t}" if start_t and end_t else ""

        rows.append({
            "Ngày": a.get("day", ""),
            "Tiết": p_str,
            "Thời gian": time_str,
            "Môn học": a.get("course_name", ""),
            "Mã lớp học phần": a.get("section_id", ""),
            "Lớp sinh viên": a.get("student_group_name", "") or a.get("student_group_id", ""),
            "Giảng viên": a.get("lecturer_name", "") or a.get("lecturer_id", ""),
            "Phòng": a.get("room_name", "") or a.get("room_id", ""),
            "Cơ sở": a.get("campus_id", ""),
        })
    return pd.DataFrame(rows)


def main():
    # 1. Header
    st.title("Hệ thống xếp thời khóa biểu tự động")
    st.subheader("Hybrid Genetic Algorithm + Repair Engine")
    st.markdown("---")

    query_data, meta = load_production_data()

    # Data missing check
    if query_data is None or "assignments" not in query_data:
        st.warning(
            "⚠️ **Chưa có dữ liệu thời khóa biểu.**\n\n"
            "Hãy chạy:\n"
            "```bash\n"
            "uv run python main.py\n"
            "```\n"
            "sau đó tải lại giao diện."
        )
        st.stop()

    assignments = query_data.get("assignments", [])
    service = ScheduleQueryService("outputs/production/schedule_query_data.json")

    # 2. Trạng thái lịch (Metrics Banner)
    st.markdown("### 📊 Trạng thái lịch sản phẩm")
    col1, col2, col3, col4 = st.columns(4)

    hard_v = meta.get("final_hard_violations", meta.get("hard_violations", 0))
    soft_p = meta.get("final_soft_penalty", meta.get("soft_penalty", 0))
    total_sec = len(assignments)
    gen_time = meta.get("generated_at", meta.get("timestamp", "N/A"))
    if isinstance(gen_time, str) and "T" in gen_time:
        gen_time = gen_time.replace("T", " ")[:19]

    with col1:
        st.metric("Hard violations", hard_v, delta="Hợp lệ (0)" if hard_v == 0 else f"{hard_v} vi phạm", delta_color="normal" if hard_v == 0 else "inverse")
    with col2:
        st.metric("Soft penalty", soft_p)
    with col3:
        st.metric("Số lớp học phần", total_sec)
    with col4:
        st.metric("Thời gian tạo lịch", str(gen_time))

    st.markdown("---")

    # 3. Sidebar Filters
    st.sidebar.header("🔍 Bộ lọc thời khóa biểu")
    
    # Populate filter options dynamically from actual data
    available_days = sorted(list({a["day"] for a in assignments if a.get("day")}), key=lambda d: DAY_ORDER.get(d, 99))
    available_groups = sorted(list({a["student_group_name"] for a in assignments if a.get("student_group_name")}))
    available_lecturers = sorted(list({a["lecturer_name"] for a in assignments if a.get("lecturer_name")}))
    available_rooms = sorted(list({a["room_name"] for a in assignments if a.get("room_name")}))
    available_courses = sorted(list({a["course_name"] for a in assignments if a.get("course_name")}))
    available_campuses = sorted(list({a["campus_id"] for a in assignments if a.get("campus_id")}))

    sel_days = st.sidebar.multiselect("Ngày", available_days)
    sel_groups = st.sidebar.multiselect("Lớp sinh viên", available_groups)
    sel_lecturers = st.sidebar.multiselect("Giảng viên", available_lecturers)
    sel_rooms = st.sidebar.multiselect("Phòng", available_rooms)
    sel_courses = st.sidebar.multiselect("Môn học", available_courses)
    sel_campuses = st.sidebar.multiselect("Cơ sở", available_campuses)

    st.sidebar.markdown("---")

    # 7. Download Button in Sidebar
    excel_file_path = Path("outputs/production/best_timetable.xlsx")
    if excel_file_path.exists():
        with open(excel_file_path, "rb") as f:
            st.sidebar.download_button(
                label="Tải thời khóa biểu Excel",
                data=f.read(),
                file_name="best_timetable.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    else:
        st.sidebar.warning("⚠️ Chưa có file Excel best_timetable.xlsx")

    # 3. Trợ lý tra cứu bằng câu hỏi tự nhiên
    st.markdown("### 💬 Trợ lý tra cứu thời khóa biểu")

    # Quick query buttons
    st.markdown("**Truy vấn nhanh theo ngày:**")
    button_cols = st.columns(len(available_days))
    quick_selected_day = None
    for idx, day_name in enumerate(available_days):
        with button_cols[idx]:
            if st.button(day_name, use_container_width=True):
                quick_selected_day = day_name

    query_input = st.text_input(
        label="Nhập câu hỏi tra cứu thời khóa biểu:",
        placeholder="VD: Lịch thứ 2, Lịch thứ 3 của lớp CNTT1, Giảng viên GV01 dạy khi nào?, Lịch phòng A9-205...",
        key="query_input_text"
    )

    btn_search = st.button("Tra cứu", type="primary")

    # Determine resulting assignments
    display_assignments = []
    text_response = ""

    if quick_selected_day:
        res = service.query(f"Lịch {quick_selected_day}")
        display_assignments = res.assignments
        text_response = ResponseFormatter.format_text(res)
    elif (btn_search or query_input.strip()) and query_input.strip():
        res = service.query(query_input.strip())
        display_assignments = res.assignments
        text_response = ResponseFormatter.format_text(res)
    else:
        # Apply sidebar filters if selected, otherwise show all
        filtered = list(assignments)
        if sel_days:
            filtered = [a for a in filtered if a.get("day") in sel_days]
        if sel_groups:
            filtered = [a for a in filtered if a.get("student_group_name") in sel_groups or a.get("student_group_id") in sel_groups]
        if sel_lecturers:
            filtered = [a for a in filtered if a.get("lecturer_name") in sel_lecturers or a.get("lecturer_id") in sel_lecturers]
        if sel_rooms:
            filtered = [a for a in filtered if a.get("room_name") in sel_rooms or a.get("room_id") in sel_rooms]
        if sel_courses:
            filtered = [a for a in filtered if a.get("course_name") in sel_courses or a.get("course_id") in sel_courses]
        if sel_campuses:
            filtered = [a for a in filtered if a.get("campus_id") in sel_campuses]

        display_assignments = filtered
        if sel_days or sel_groups or sel_lecturers or sel_rooms or sel_courses or sel_campuses:
            text_response = f"Hiển thị {len(display_assignments)} lớp học phần thỏa mãn các bộ lọc."
        else:
            text_response = f"Hiển thị toàn bộ {len(display_assignments)} lớp học phần trong thời khóa biểu."

    # 6. Results Display
    st.markdown("### 📋 Kết quả")
    st.info(text_response)

    if display_assignments:
        df_display = format_dataframe(display_assignments)
        st.dataframe(df_display, use_container_width=True, hide_index=True)
    else:
        st.warning("Không tìm thấy lịch phù hợp với yêu cầu.")


if __name__ == "__main__":
    main()
