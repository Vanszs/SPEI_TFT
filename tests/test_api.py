import sys
from pathlib import Path
import pytest
from datetime import date
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app

@pytest.mark.asyncio
async def test_study_regions_freshness_contract():
    processed = Path(__file__).resolve().parent.parent / "data/processed/spei_dataset.parquet"
    if not processed.exists():
        pytest.skip("processed parquet is absent")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as ac:
        res = await ac.get("/api/v1/study/regions")
    assert res.status_code == 200
    body = res.json()
    assert body["schema_version"] == 3
    assert date.fromisoformat(body["as_of"]) <= date.today()
    import pandas as pd
    import json
    artifact_path = Path(__file__).resolve().parent.parent / "frontend/public/forecast_30d.json"
    if artifact_path.exists():
        expected_as_of = date.fromisoformat(json.loads(artifact_path.read_text())["last_observed"])
    else:
        observed = pd.read_parquet(processed, columns=["time"])["time"]
        expected_as_of = pd.to_datetime(observed).max().date()
    assert body["as_of"] == expected_as_of.isoformat()
    assert body["data_age_days"] == (date.today() - expected_as_of).days
    assert body["freshness"] in {"current", "stale"}
    assert body["forecast_status"] in {"active", "archived"}
    run_config = Path(__file__).resolve().parent.parent / "logs/run_config.json"
    if run_config.exists():
        active = Path(json.loads(run_config.read_text())["best_model_path"]).name
        assert body["model"]["checkpoint"] == active
    assert isinstance(body["data_age_days"], int)
    assert body["freshness"] in {"current", "stale", "archived"}
    assert body["forecast_status"] in {"active", "archived"}
    assert isinstance(body["model"], dict)
    assert {"checkpoint", "skill_score_t1", "skill_score_all_horizons", "picp", "rmse", "mae", "test_period"} <= body["model"].keys()

@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as ac:
        res = await ac.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert "status" in data

@pytest.mark.asyncio
async def test_predict_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as ac:
        payload = {"city_id": "Bojonegoro", "forecast_days": 5}
        res = await ac.post("/api/v1/predict", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["city_id"] == "Bojonegoro"
        assert len(data["predictions"]["p50"]) == 5
        assert len(data["dates"]) == 5

@pytest.mark.asyncio
async def test_spei_calculate_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as ac:
        payload = {"precipitation": [10.0, 5.0], "evapotranspiration": [2.0, 3.0], "scale": 3}
        res = await ac.post("/api/v1/spei/calculate", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert len(data["water_deficit"]) == 2

@pytest.mark.asyncio
async def test_ingest_status_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as ac:
        res = await ac.get("/api/v1/ingest/status")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "synced"

@pytest.mark.asyncio
async def test_stream_weather_sse():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as ac:
        res = await ac.get("/api/v1/stream/weather?city_id=Bojonegoro&interval=0.1&max_steps=1")
        assert res.status_code == 200
        assert "text/event-stream" in res.headers.get("content-type", "")
        lines = res.text.splitlines()
        assert any("weather_update" in line or "weather_sync" in line for line in lines)
