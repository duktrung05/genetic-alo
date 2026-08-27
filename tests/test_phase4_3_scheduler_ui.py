from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "ui_app.py"


def test_scheduler_product_header_and_compact_easy_dataset_card():
    app = AppTest.from_file(APP_PATH).run(timeout=20)
    assert not app.exception
    assert app.title[0].value == "AI Timetable Scheduler"
    assert app.selectbox[0].value == "EASY"
    assert app.button[0].label == "✨ Generate Timetable"
    assert any("Valid" in message.value for message in app.success)

    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics == {
        "Sections": "62", "Activities": "62", "Lecturers": "15",
        "Student Groups": "12", "Rooms": "11", "Timeslots": "96",
    }
    markdown = "\n".join(item.value for item in app.markdown)
    assert "Final Hybrid Method" in markdown
    assert all(label in markdown for label in ("GA", "Repair", "SLS"))


@pytest.mark.integration
def test_scheduler_result_hierarchy_navigation_and_excel_shortcut():
    app = AppTest.from_file(APP_PATH).run(timeout=20)
    app.button[0].click().run(timeout=90)
    assert not app.exception

    result = app.session_state["demo_result"]
    assert result["run"]["hard_violations"] == 0
    assert result["run"]["scheduled_count"] == 62
    assert result["run"]["activity_count"] == 62
    assert any("Feasible Timetable" in message.value for message in app.success)

    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Hard Violations"] == "0"
    assert "Soft Score" in metrics
    assert metrics["Runtime"].endswith("s")
    assert metrics["Scheduled"] == "62 / 62"
    assert "First feasible solution:" in "\n".join(item.value for item in app.caption)

    assert [button.label for button in app.button[-2:]] == ["View Timetable", "Ask Schedule"]
    assert len(app.download_button) == 1
    assert app.download_button[0].label == "Export Excel"

    next(button for button in app.button if button.label == "View Timetable").click().run(timeout=20)
    assert app.title[0].value == "Timetable"
    assert len(app.download_button) == 3

    app.sidebar.radio[0].set_value("Scheduler").run(timeout=20)
    next(button for button in app.button if button.label == "Ask Schedule").click().run(timeout=20)
    assert app.title[0].value == "Ask Schedule"
    assert app.metric[0].value == "EASY"
    assert not app.exception

