interface ObservedSeries {
  dates: string[];
  spei: number[];
}

interface ForecastSeries {
  dates: string[];
  p10: number[];
  p50: number[];
  p90: number[];
}

export interface CityForecast {
  entity: string;
  observed: ObservedSeries;
  forecast: ForecastSeries;
}

export interface ForecastData {
  checkpoint: string;
  last_observed: string;
  observed_days: number;
  forecast_days: number;
  severity_thresholds: { moderate: number; severe: number; extreme: number };
  cities: Record<string, CityForecast>;
}

export interface DayPoint {
  date: string;
  day: number;
  monthLabel: string;
  isForecast: boolean;
  spei: number;
  p10?: number;
  p50?: number;
  p90?: number;
}

type DroughtClass = 'NORMAL' | 'MODERATE' | 'SEVERE' | 'EXTREME';

const SHORT_MONTH = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];
const LONG_MONTH = [
  'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
  'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember',
];

/** Hanya 30 hari terakhir observasi + 30 hari prediksi — tidak ada interpolasi bulanan. */
export async function loadForecast30d(signal?: AbortSignal): Promise<ForecastData> {
  const response = await fetch('/forecast_30d.json', { signal });
  if (!response.ok) throw new Error(`Artefak prediksi 30 hari tidak ditemukan (${response.status})`);
  return (await response.json()) as ForecastData;
}

/** Kanonik, mengikuti src/data/spei.py:classify_spei. Ambang, bukan tafsiran bebas. */
export function classify(spei: number, t: ForecastData['severity_thresholds']): DroughtClass {
  if (spei <= t.extreme) return 'EXTREME';
  if (spei <= t.severe) return 'SEVERE';
  if (spei <= t.moderate) return 'MODERATE';
  return 'NORMAL';
}

export const CLASS_LABEL: Record<DroughtClass, string> = {
  NORMAL: 'Normal',
  MODERATE: 'Waspada',
  SEVERE: 'Siaga',
  EXTREME: 'Awas',
};

export function monthTitle(date: string): string {
  const d = new Date(`${date}T00:00:00`);
  return `${LONG_MONTH[d.getMonth()]} ${d.getFullYear()}`;
}

/** Hanya 30 hari prediksi ke depan — tanpa seri observasi. */
export function toForecastSeries(city: CityForecast): DayPoint[] {
  return city.forecast.dates.map((date, i) => ({
    date,
    day: new Date(`${date}T00:00:00`).getDate(),
    monthLabel: short(date),
    isForecast: true,
    spei: city.forecast.p50[i],
    p10: city.forecast.p10[i],
    p50: city.forecast.p50[i],
    p90: city.forecast.p90[i],
  }));
}

/** Nilai observasi terakhir — satu angka acuan, bukan seri. */
export function lastObserved(city: CityForecast): number | null {
  return city.observed.spei.at(-1) ?? null;
}

function short(date: string): string {
  const d = new Date(`${date}T00:00:00`);
  return `${d.getDate()} ${SHORT_MONTH[d.getMonth()]}`;
}

export function dayLabel(date: string): string {
  const d = new Date(`${date}T00:00:00`);
  return `${d.getDate()} ${SHORT_MONTH[d.getMonth()]} ${d.getFullYear()}`;
}