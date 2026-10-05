"""
FastAPI Backend Architecture for SPEI Drought Monitoring System.
Includes REST endpoints and SSE/WebSocket real-time streaming for live weather & inference state.
"""

import asyncio
import json
import os
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field
import uvicorn
from pathlib import Path
import numpy as np
import pandas as pd

from src.data.spei import calculate_spei, classify_spei


# --- Pydantic Schemas ---

class PredictRequest(BaseModel):
    city_id: str = Field(..., example="Bojonegoro", description="City identifier")
    forecast_days: int = Field(default=30, ge=1, le=30, description="Forecast horizon in days (model max 30)")

class QuantilePredictions(BaseModel):
    p10: List[float] = Field(..., description="10th percentile SPEI predictions")
    p50: List[float] = Field(..., description="50th percentile (median) SPEI predictions")
    p90: List[float] = Field(..., description="90th percentile SPEI predictions")

class StudyQuantiles(BaseModel):
    p10: float
    p50: float
    p90: float

class PredictResponse(BaseModel):
    city_id: str
    dates: List[str]
    predictions: QuantilePredictions
    drought_risk_level: str = Field(..., example="Moderate Drought")

class SPEICalculateRequest(BaseModel):
    precipitation: List[float] = Field(..., description="Daily precipitation in mm")
    evapotranspiration: List[float] = Field(..., description="Daily FAO PET in mm")
    scale: int = Field(default=3, description="SPEI time scale in months")

class SPEICalculateResponse(BaseModel):
    water_deficit: List[float]
    spei: List[Optional[float]]

class IngestionStatusResponse(BaseModel):
    status: str
    last_sync: str
    nodes_synced: int

class StudyGridCell(BaseModel):
    id: str
    city_id: str
    lat: float
    lon: float
    spei: float
    selected_rank: Optional[int] = None

class StudyRegionResponse(BaseModel):
    id: str
    regency_name: str
    province: str
    coordinates: List[float]
    spei_current: float
    severity: str
    latest_observation: str
    evaluation_prediction: Optional[StudyQuantiles] = None
    historical_spei: List[Dict[str, Any]]

class StudyResponse(BaseModel):
    data_status: str
    source: str
    observation_period: List[str]
    prediction_period: List[str]
    regions: List[StudyRegionResponse]
    grid: List[StudyGridCell]


# --- Model Management / Lifetime ---

class AppState:
    is_ready: bool = False
    bundle: Any = None
    load_error: Optional[str] = None

app_state = AppState()

def ensure_bundle():
    """Lazily build the TFT inference bundle once (checkpoint load is slow)."""
    if app_state.bundle is not None:
        return app_state.bundle
    if app_state.load_error is not None:
        return None
    try:
        from src.evaluation.inference import build_bundle

        app_state.bundle = build_bundle(
            checkpoint_path=os.getenv("TFT_CHECKPOINT_PATH") or None
        )
        app_state.is_ready = True
    except Exception as exc:
        app_state.bundle = None
        app_state.load_error = str(exc)
        app_state.is_ready = False
    return app_state.bundle

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: eager-load so /health reflects real readiness; endpoint also re-checks.
    ensure_bundle()
    yield
    app_state.bundle = None

app = FastAPI(
    title="TFT Drought Monitoring & SPEI API",
    description="Production backend API for Temporal Fusion Transformer drought prediction and OpenMeteo SPEI calculation.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],  # REST + WS verb support
    allow_headers=["*"],
)

def _study_paths() -> tuple[Path, Path]:
    root = Path(__file__).resolve().parent.parent
    return root / "data/processed/spei_dataset.parquet", root / "results/full_eval_20260602_063310/predictions_full.csv"

def _spei_label(value: float) -> str:
    # 4-class frontend contract (NORMAL|MODERATE|SEVERE|EXTREME).
    # Boundaries mirror the canonical WMO classes in src.data.spei.classify_spei.
    if value <= -2.0: return "EXTREME"
    if value <= -1.5: return "SEVERE"
    if value <= -1.0: return "MODERATE"
    return "NORMAL"

@app.get("/api/v1/study/regions", response_model=StudyResponse, tags=["Study"])
async def study_regions():
    """Expose verified thesis artifacts; no fabricated future forecast."""
    data_path, pred_path = _study_paths()
    raw_path = data_path.parent.parent / "raw/weather_history_east_java.parquet"
    if not data_path.exists() or not pred_path.exists():
        raise HTTPException(status_code=503, detail="Artefak data penelitian belum tersedia.")
    data = pd.read_parquet(data_path, columns=["city_id", "time", "SPEI_3", "lat", "lon"])
    data["time"] = pd.to_datetime(data["time"])
    preds = pd.read_csv(pred_path, usecols=["city_id", "time", "pred_p10", "pred_p50", "pred_p90"])
    preds["time"] = pd.to_datetime(preds["time"])
    grid = []
    city_centers = {}
    selection_path = data_path.parent / "node_selection_v2.parquet"
    if selection_path.exists():
        selection = pd.read_parquet(
            selection_path,
            columns=["city_id", "raw_node_id", "lat", "lon", "selected_rank", "selected_flag"],
        )
        selection = selection[selection["selected_flag"] == True].sort_values(["city_id", "selected_rank"])
        latest_spei = data.sort_values("time").groupby("city_id")["SPEI_3"].last().to_dict()
        for city, city_rows in selection.groupby("city_id"):
            top = city_rows.iloc[0]
            city_centers[str(city)] = [float(top["lat"]), float(top["lon"])]
            for row in city_rows.itertuples():
                grid.append(
                    StudyGridCell(
                        id=str(row.raw_node_id),
                        city_id=str(city),
                        lat=float(row.lat),
                        lon=float(row.lon),
                        spei=float(latest_spei.get(city, 0)),
                        selected_rank=int(row.selected_rank),
                    )
                )
    elif raw_path.exists():
        raw = pd.read_parquet(raw_path, columns=["city_id", "node_local_id", "lat", "lon"])
        latest_spei = data.sort_values("time").groupby("city_id")["SPEI_3"].last().to_dict()
        raw_points = raw.drop_duplicates(["city_id", "lat", "lon"]).copy()
        selected_indices = set()
        for city, city_points in raw_points.groupby("city_id"):
            center = city_points.loc[city_points["node_local_id"] == "n00"].iloc[0]
            city_centers[str(city)] = [float(center["lat"]), float(center["lon"])]
            selected_indices.add(center.name)
            corners = ["n05", "n06", "n07", "n08"]
            for cid in corners:
                match = city_points[city_points["node_local_id"] == cid]
                if not match.empty:
                    selected_indices.add(match.index[0])
        for row in raw_points.loc[sorted(selected_indices)].itertuples():
            city = str(row.city_id)
            grid.append(
                StudyGridCell(
                    id=f"{city}:{row.lat}:{row.lon}",
                    city_id=city,
                    lat=float(row.lat),
                    lon=float(row.lon),
                    spei=float(latest_spei.get(city, 0)),
                )
            )
    regions = []
    for city in sorted(data["city_id"].astype(str).unique()):
        city_data = data[data["city_id"].astype(str) == city].sort_values("time")
        city_preds = preds[preds["city_id"].astype(str) == city].sort_values("time")
        pred_by_date = {
            pd.Timestamp(r.time).date().isoformat(): float(r.pred_p50)
            for r in city_preds.itertuples()
        }
        latest = city_data.iloc[-1]
        latest_pred = city_preds.iloc[-1] if not city_preds.empty else None
        regions.append(StudyRegionResponse(
            id=city,
            regency_name=f"Kab. {city}",
            province="Jawa Timur",
            coordinates=city_centers.get(city, [float(latest["lat"]), float(latest["lon"])]),
            spei_current=float(latest["SPEI_3"]),
            severity=_spei_label(float(latest["SPEI_3"])),
            latest_observation=latest["time"].date().isoformat(),
            evaluation_prediction=(StudyQuantiles(p10=float(latest_pred["pred_p10"]), p50=float(latest_pred["pred_p50"]), p90=float(latest_pred["pred_p90"])) if latest_pred is not None else None),
            historical_spei=[
                {
                    "month": row.time.strftime("%d %b %Y"),
                    "actual": float(row.SPEI_3),
                    "predicted": pred_by_date.get(row.time.date().isoformat()),
                }
                for row in city_data.tail(6).itertuples()
            ],
        ))
    return StudyResponse(
        data_status="DATA PENELITIAN · observasi dan evaluasi model",
        source="data/processed/spei_dataset.parquet + results/full_eval_20260602_063310/predictions_full.csv",
        observation_period=[data["time"].min().date().isoformat(), data["time"].max().date().isoformat()],
        prediction_period=[preds["time"].min().date().isoformat(), preds["time"].max().date().isoformat()],
        regions=regions,
        grid=grid,
    )


# --- REST Endpoints ---

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy" if app_state.is_ready else "degraded",
        "model_loaded": app_state.is_ready
    }

@app.post("/api/v1/predict", response_model=PredictResponse, tags=["Prediction"])
async def predict_spei(payload: PredictRequest):
    """
    Generate a real SPEI forecast from the loaded TFT checkpoint.
    """
    bundle = ensure_bundle()
    if bundle is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Model not available: {app_state.load_error or 'not loaded'}",
        )
    try:
        out = bundle.forecast(payload.city_id, payload.forecast_days)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    p50 = out["p50"]
    return PredictResponse(
        city_id=payload.city_id,
        dates=out["dates"],
        predictions=QuantilePredictions(p10=out["p10"], p50=p50, p90=out["p90"]),
        drought_risk_level=_spei_label(float(np.median(p50))),
    )

@app.post("/api/v1/spei/calculate", response_model=SPEICalculateResponse, tags=["SPEI"])
async def calculate_spei_endpoint(payload: SPEICalculateRequest):
    """
    Calculate SPEI water deficit and index from raw P and ET0 series.
    """
    if len(payload.precipitation) != len(payload.evapotranspiration):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Precipitation and Evapotranspiration series length mismatch."
        )
    
    deficit = [p - et for p, et in zip(payload.precipitation, payload.evapotranspiration)]
    # Real SPEI via the canonical implementation. Daily series indexed to a
    # contiguous date range so the month-based fisk fit has a valid index.
    index = pd.date_range(start="2000-01-01", periods=len(deficit), freq="D")
    series = pd.Series(deficit, index=index, dtype=float)
    spei_series = calculate_spei(series, scale=payload.scale)
    spei_res = [None if pd.isna(v) else float(v) for v in spei_series]

    return SPEICalculateResponse(water_deficit=deficit, spei=spei_res)

@app.get("/api/v1/ingest/status", response_model=IngestionStatusResponse, tags=["Ingestion"])
async def ingest_status():
    """
    Real ingestion/pipeline status derived from the processed dataset artifact.
    """
    root = Path(__file__).resolve().parent.parent
    raw_path = root / "data/raw/weather_history_east_java.parquet"
    proc_path = root / "data/processed/spei_dataset.parquet"
    if not proc_path.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Artefak data penelitian belum tersedia.",
        )
    nodes = 0
    if raw_path.exists():
        raw = pd.read_parquet(raw_path, columns=["raw_node_id"])
        nodes = int(raw["raw_node_id"].nunique())
    last_sync = datetime.utcfromtimestamp(proc_path.stat().st_mtime).isoformat() + "Z"
    return IngestionStatusResponse(status="synced", last_sync=last_sync, nodes_synced=nodes)


# --- Real-Time Streaming: SSE & WebSocket ---

# 1. SSE Stream: Latest real weather observations & inference state
def _latest_weather(city_id: str) -> dict:
    """Most recent real weather observations + latest SPEI for a city."""
    root = Path(__file__).resolve().parent.parent
    proc_path = root / "data/processed/spei_dataset.parquet"
    if not proc_path.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Artefak data penelitian belum tersedia.",
        )
    per_city = globals().setdefault("_WEATHER_CACHE", {})
    if city_id not in per_city:
        cols = [
            "city_id", "time", "SPEI_3", "temperature_2m_max",
            "relative_humidity_2m_mean", "precipitation_sum",
            "et0_fao_evapotranspiration",
        ]
        df = pd.read_parquet(proc_path, columns=cols).sort_values("time")
        per_city[city_id] = df[df["city_id"].astype(str) == city_id].tail(1)
    row = per_city[city_id]
    if row.empty:
        raise KeyError(f"Unknown city: {city_id}")
    r = row.iloc[0]
    return {
        "temp_c": float(r["temperature_2m_max"]),
        "humidity_pct": float(r["relative_humidity_2m_mean"]),
        "precip_mm": float(r["precipitation_sum"]),
        "et0_mm": float(r["et0_fao_evapotranspiration"]),
        "spei": float(r["SPEI_3"]),
        "observed_at": pd.Timestamp(r["time"]).date().isoformat(),
    }

async def weather_inference_generator(city_id: str, interval: float = 3.0, max_steps: Optional[int] = None) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Generator streaming the latest real weather observations, ingestion status,
    and TFT readiness state over Server-Sent Events.
    """
    step = 0
    while True:
        step += 1
        latest = _latest_weather(city_id)
        payload = {
            "type": "weather_sync",
            "city_id": city_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "step": step,
            "weather": {
                "temp_c": latest["temp_c"],
                "humidity_pct": latest["humidity_pct"],
                "precip_mm": latest["precip_mm"],
                "et0_mm": latest["et0_mm"],
                "observed_at": latest["observed_at"],
            },
            "inference_state": {
                "model_status": "ready" if app_state.is_ready else "unavailable",
                "latest_spei_p50": latest["spei"],
                "drought_risk": classify_spei(latest["spei"]),
            }
        }
        yield {
            "event": "weather_update",
            "data": json.dumps(payload)
        }
        if max_steps and step >= max_steps:
            break
        await asyncio.sleep(interval)

@app.get("/api/v1/stream/weather", tags=["Streaming"])
async def stream_weather_events(
    city_id: str = Query("Bojonegoro"), 
    interval: float = Query(3.0, ge=0.1, le=10.0),
    max_steps: Optional[int] = Query(None, description="Optional cap on stream iterations for testing")
):
    """
    Server-Sent Events (SSE) endpoint streaming live weather sync & inference state.
    """
    return EventSourceResponse(weather_inference_generator(city_id=city_id, interval=interval, max_steps=max_steps))


# 2. WebSocket Stream: Bidirectional Monitoring & Control
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws/monitoring")
async def websocket_monitoring(websocket: WebSocket):
    """
    WebSocket endpoint for real-time monitoring and streaming live updates.
    """
    await manager.connect(websocket)
    try:
        # Send initial connection acknowledgment
        await websocket.send_text(json.dumps({"event": "connected", "message": "Connected to SPEI Live Monitor Stream"}))
        while True:
            data = await websocket.receive_text()
            # Respond to incoming messages or control signals
            response = {
                "event": "message_ack",
                "received": data,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            await websocket.send_text(json.dumps(response))
    except WebSocketDisconnect:
        manager.disconnect(websocket)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
