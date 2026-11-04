import type { Freshness, ModelMetrics, RegionPrediction } from './types';

interface StudyResponse {
  schema_version: number;
  as_of: string;
  data_age_days: number;
  freshness: Freshness;
  forecast_status: 'active' | 'archived';
  model: {
    checkpoint: string | null;
    skill_score_t1: number | null;
    skill_score_all_horizons: number | null;
    picp: number | null;
    rmse: number | null;
    mae: number | null;
    n: number | null;
    test_period: string | null;
  };
  data_status: string;
  source: string;
  observation_period: string[];
  prediction_period: string[];
  regions: Array<{
    id: string;
    regency_name: string;
    province: string;
    coordinates: [number, number];
    spei_current: number;
    severity: RegionPrediction['severity'];
    latest_observation: string;
    evaluation_prediction: { p10: number; p50: number; p90: number } | null;
    historical_spei: Array<{ month: string; actual: number | null; predicted: number | null }>;
  }>;
}

export interface StudyData {
  regions: RegionPrediction[];
  status: string;
  source: string;
  observationPeriod: string[];
  predictionPeriod: string[];
  asOf: string;
  dataAgeDays: number;
  freshness: Freshness;
  forecastStatus: 'active' | 'archived';
  model: ModelMetrics;
}

export async function fetchStudyData(signal?: AbortSignal): Promise<StudyData> {
  const response = await fetch('/api/v1/study/regions', { signal });
  if (!response.ok) throw new Error(`Data penelitian tidak tersedia (HTTP ${response.status}).`);
  return mapPayload((await response.json()) as StudyResponse);
}

function mapPayload(payload: StudyResponse): StudyData {
  const model = payload.model ?? {};
  return {
    status: payload.data_status,
    source: payload.source,
    observationPeriod: payload.observation_period,
    predictionPeriod: payload.prediction_period,
    asOf: payload.as_of,
    dataAgeDays: payload.data_age_days,
    freshness: payload.freshness,
    forecastStatus: payload.forecast_status,
    model: {
      checkpoint: model.checkpoint ?? null,
      skillScoreT1: model.skill_score_t1 ?? null,
      skillScoreAllHorizons: model.skill_score_all_horizons ?? null,
      picp: model.picp ?? null,
      rmse: model.rmse ?? null,
      mae: model.mae ?? null,
      n: model.n ?? null,
      testPeriod: model.test_period ?? null,
    },
    regions: (payload.regions ?? []).map((region) => ({
      id: region.id,
      regencyName: region.regency_name,
      province: region.province,
      speiCurrent: region.spei_current,
      // evaluation_prediction is the t+1 evaluation point, not a multi-horizon forecast.
      speiForecast: {
        q10: region.evaluation_prediction?.p10 ?? region.spei_current,
        q50: region.evaluation_prediction?.p50 ?? region.spei_current,
        q90: region.evaluation_prediction?.p90 ?? region.spei_current,
      },
      severity: region.severity,
      coordinates: region.coordinates,
      historicalSpei: region.historical_spei ?? [],
    })),
  };
}
