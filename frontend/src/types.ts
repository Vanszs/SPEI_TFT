export type DroughtSeverity = 'NORMAL' | 'MODERATE' | 'SEVERE' | 'EXTREME';
export type Freshness = 'current' | 'stale';

export interface QuantileForecast {
  q10: number; // Worst case scenario (10th percentile)
  q50: number; // Median prediction (50th percentile)
  q90: number; // Best case scenario (90th percentile)
}

export interface HistoricalPoint {
  month: string;
  actual: number | null;
  predicted: number | null;
}

export interface RegionPrediction {
  id: string;
  regencyName: string;
  province: string;
  speiCurrent: number;
  speiForecast: QuantileForecast;
  severity: DroughtSeverity;
  coordinates: [number, number]; // [lat, lng]
  historicalSpei: HistoricalPoint[];
}

/** Model metrics come from the evaluation of the checkpoint that serves the API. */
export interface ModelMetrics {
  checkpoint: string | null;
  skillScoreT1: number | null;
  skillScoreAllHorizons: number | null;
  picp: number | null;
  rmse: number | null;
  mae: number | null;
  n: number | null;
  testPeriod: string | null;
}
