import json

import pytest


@pytest.mark.unit
def test_load_production_data_returns_query_and_metadata(tmp_path, monkeypatch):
    from ui_app import load_production_data

    production_dir = tmp_path / "outputs" / "production"
    production_dir.mkdir(parents=True)
    query_data = {"assignments": [{"section_id": "SEC1"}]}
    metadata = {"primary_method": "ga_repair_sls"}
    (production_dir / "schedule_query_data.json").write_text(
        json.dumps(query_data), encoding="utf-8"
    )
    (production_dir / "best_timetable_metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    loaded_query, loaded_metadata = load_production_data()

    assert loaded_query == query_data
    assert loaded_metadata == metadata


@pytest.mark.unit
def test_method_display_name_normalizes_legacy_production_metadata():
    from ui_app import get_method_display_name

    metadata = {
        "method": "Hybrid GA + Repair + Post-Search SLS",
        "primary_method": "hybrid",
        "soft_local_search_enabled": True,
    }

    assert get_method_display_name(metadata) == "GA + Repair + SLS (Production)"


@pytest.mark.unit
def test_method_display_name_uses_canonical_method_id():
    from ui_app import get_method_display_name

    assert get_method_display_name({"primary_method": "ga_repair"}) == "GA + Repair"
    assert get_method_display_name({"primary_method": "ga_repair_sls"}) == (
        "GA + Repair + SLS (Production)"
    )


@pytest.mark.unit
def test_text_query_runs_only_after_explicit_submit():
    from ui_app import should_run_text_query

    assert should_run_text_query(False, "Lịch thứ 2") is False
    assert should_run_text_query(True, "   ") is False
    assert should_run_text_query(True, "Lịch thứ 2") is True
