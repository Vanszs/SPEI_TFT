<script setup lang="ts">
import { computed } from 'vue';
import { historyMetrics, type HistoryWindow } from '../data/forecast';

const props = defineProps<{ windows: HistoryWindow[] }>();
const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];
const formatDate = (value: string) => {
  const date = new Date(`${value}T00:00:00`);
  return `${date.getDate()} ${monthNames[date.getMonth()]} ${date.getFullYear()}`;
};
const formatValue = (value: number | null) => value === null || !Number.isFinite(value) ? '—' : value.toFixed(2);
const formatPercent = (value: number | null) => value === null ? '—' : `${value.toFixed(1)}%`;
const rows = computed(() => props.windows.map((window) => {
  const metrics = historyMetrics(window);
  const finiteValues = [...window.p10, ...window.p50, ...window.p90, ...window.actual]
    .filter((value): value is number => value !== null && Number.isFinite(value));
  const low = Math.min(0, ...finiteValues);
  const high = Math.max(0, ...finiteValues);
  const span = high - low || 1;
  const x = (i: number) => 8 + (i / Math.max(window.dates.length - 1, 1)) * 284;
  const y = (value: number) => 88 - ((value - low) / span) * 76;
  // Putus garis saat ada hari tanpa realisasi; jangan menyambung celah.
  const line = (values: (number | null)[]) => {
    let path = '';
    let started = false;
    values.forEach((value, i) => {
      if (value === null || !Number.isFinite(value)) {
        started = false;
        return;
      }
      path += `${started ? ' L' : ' M'}${x(i).toFixed(1)},${y(value).toFixed(1)}`;
      started = true;
    });
    return path;
  };
  const band = window.dates.map((_, i) => `${x(i).toFixed(1)},${y(window.p10[i]).toFixed(1)}`)
    .concat(window.dates.map((_, i) => `${x(window.dates.length - 1 - i).toFixed(1)},${y(window.p90[window.dates.length - 1 - i]).toFixed(1)}`))
    .join(' ');
  const actualLine = line(window.actual);
  const start = window.dates[0];
  const end = window.dates.at(-1) ?? start;
  const metricsLabel = `MAE ${formatValue(metrics.mae)}, cakupan ${formatPercent(metrics.coverage)}`;
  return { window, metrics, band, medianLine: line(window.p50), actualLine, zeroY: y(0), period: `${formatDate(start)} – ${formatDate(end)}`, metricsLabel };
}));
const averages = computed(() => {
  const mean = (key: 'mae' | 'coverage') => {
    const values = rows.value.map(({ metrics }) => metrics[key]).filter((value): value is number => value !== null);
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  };
  return { mae: mean('mae'), coverage: mean('coverage') };
});
</script>

<template>
  <section class="history" aria-labelledby="history-title">
    <header class="history__head">
      <div>
        <span class="eyebrow">Riwayat prediksi</span>
        <h2 id="history-title">Tiga prakiraan terakhir, dibandingkan realisasi.</h2>
        <p>Uji ulang: tiap prakiraan hanya memakai data sampai tanggal yang tercantum, 30 hari sebelum periode yang diprediksi. Ini menunjukkan rekam jejak model, bukan jaminan hasil mendatang.</p>
      </div>
    </header>
    <p class="history__summary">
      Rata-rata {{ windows.length }} jendela <span>Selisih <b>{{ formatValue(averages.mae) }}</b></span>
      <span>Hari dalam rentang <b>{{ formatPercent(averages.coverage) }}</b></span>
    </p>
    <div class="history__grid">
      <article v-for="(row, index) in rows" :key="row.window.as_of" class="history__item">
        <div class="history__item-head">
          <div><span class="history__index">JENDELA {{ String(index + 1).padStart(2, '0') }}</span><h3>{{ row.period }}</h3></div>
          <span class="history__asof">data sampai {{ formatDate(row.window.as_of) }}</span>
        </div>
        <dl class="history__metrics">
          <div><dt>Rata-rata selisih</dt><dd>{{ formatValue(row.metrics.mae) }}</dd></div>
          <div><dt>Selisih terbesar (RMSE)</dt><dd>{{ formatValue(row.metrics.rmse) }}</dd></div>
          <div><dt>Hari dalam rentang</dt><dd>{{ formatPercent(row.metrics.coverage) }}</dd></div>
        </dl>
        <svg class="history__chart" viewBox="0 0 300 100" role="img" :aria-label="`Realisasi dan prakiraan ${row.period}: ${row.metricsLabel}`">
          <line x1="8" x2="292" :y1="row.zeroY" :y2="row.zeroY" class="history__zero" />
          <polygon :points="row.band" class="history__band" />
          <path :d="row.medianLine" class="history__median" />
          <path :d="row.actualLine" class="history__actual" />
        </svg>
        <div class="history__legend" aria-hidden="true"><span><i class="history__key--band"></i>P10–P90</span><span><i class="history__key--median"></i>P50</span><span><i class="history__key--actual"></i>Realisasi</span></div>
        <details class="history__details">
          <summary>Lihat nilai harian</summary>
          <div class="chart__table">
            <table>
              <caption>Nilai harian prakiraan dan realisasi, {{ row.period }}</caption>
              <thead><tr><th scope="col">Hari</th><th scope="col">Tanggal</th><th scope="col">P50</th><th scope="col">P10</th><th scope="col">P90</th><th scope="col">Aktual</th></tr></thead>
              <tbody><tr v-for="(date, day) in row.window.dates" :key="date"><th scope="row">{{ day + 1 }}</th><td>{{ formatDate(date) }}</td><td>{{ formatValue(row.window.p50[day]) }}</td><td>{{ formatValue(row.window.p10[day]) }}</td><td>{{ formatValue(row.window.p90[day]) }}</td><td>{{ formatValue(row.window.actual[day]) }}</td></tr></tbody>
            </table>
          </div>
        </details>
      </article>
    </div>
  </section>
</template>
