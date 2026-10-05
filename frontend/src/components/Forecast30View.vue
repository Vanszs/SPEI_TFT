<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { RefreshCw } from 'lucide-vue-next';
import Forecast30Chart from './Forecast30Chart.vue';
import ForecastMetrics from './ForecastMetrics.vue';
import {
  CLASS_LABEL,
  classify,
  lastObserved,
  loadForecast30d,
  monthTitle,
  toForecastSeries,
  type ForecastData,
} from '../data/forecast';

const data = ref<ForecastData | null>(null);
const error = ref<string | null>(null);
const city = ref<string | null>(null);
let controller: AbortController | null = null;

function load() {
  controller?.abort();
  controller = new AbortController();
  error.value = null;
  loadForecast30d(controller.signal)
    .then((d) => {
      data.value = d;
      city.value = city.value && d.cities[city.value] ? city.value : Object.keys(d.cities)[0];
    })
    .catch((e: unknown) => {
      if ((e as Error).name !== 'AbortError') error.value = (e as Error).message;
    });
}

onMounted(load);
onUnmounted(() => controller?.abort());

const cityNames = computed(() => (data.value ? Object.keys(data.value.cities) : []));
const current = computed(() => (data.value && city.value ? data.value.cities[city.value] : null));
const series = computed(() => (current.value ? toForecastSeries(current.value) : []));
const lastObs = computed(() => (current.value ? lastObserved(current.value) : null));
const monthSpan = computed(() => {
  if (!data.value) return '';
  const names = new Set([...series.value.map((p) => monthTitle(p.date))]);
  return [...names].join(' – ');
});
const endMedian = computed(() => current.value?.forecast.p50.at(-1) ?? null);

// Umur data harus terlihat: prakiraan dari data basi tidak sama dengan prakiraan segar.
const dataAgeDays = computed(() => {
  if (!data.value) return null;
  const last = new Date(`${data.value.last_observed}T00:00:00`);
  return Math.max(0, Math.round((Date.now() - last.getTime()) / 86400000));
});
const isStale = computed(() => dataAgeDays.value !== null && dataAgeDays.value > 7);
const endClass = computed(() =>
  data.value && endMedian.value !== null ? classify(endMedian.value, data.value.severity_thresholds) : 'NORMAL',
);
const endNote = computed(() => {
  if (!data.value || !current.value) return '';
  const last = current.value.forecast.p50.at(-1) as number;
  if (last > data.value.severity_thresholds.moderate) return 'Di atas ambang kekeringan';
  if (last > data.value.severity_thresholds.severe) return 'Kekeringan sedang';
  if (last > data.value.severity_thresholds.extreme) return 'Kekeringan parah';
  return 'Kekeringan ekstrem';
});
</script>

<template>
  <section id="prediksi-30" class="view30" aria-labelledby="prediksi-30-title">
    <div v-if="error" class="notice notice--error" role="alert">{{ error }}</div>

    <header class="view30__head">
      <div>
        <span class="eyebrow">Prediksi 30 hari ke depan</span>
        <h1 id="prediksi-30-title">Prakiraan SPEI harian hingga {{ monthSpan }}.</h1>
        <p>
          Keluaran Temporal Fusion Transformer dengan encoder 90 hari. Rentang P10–P90 adalah
          ketidakpastian model, bukan peringatan resmi.
        </p>
      </div>
      <div v-if="data" class="view30__aside">
        <span :class="['freshness', { 'freshness--stale': isStale }]">
          <span class="freshness__dot" aria-hidden="true"></span>
          Data per {{ data.last_observed }} · {{ dataAgeDays }} hari lalu{{ isStale ? ' · perlu pembaruan' : '' }}
        </span>
        <button class="ghost" type="button" @click="load">
          <RefreshCw :size="14" /> Muat ulang
        </button>
      </div>
    </header>

    <nav v-if="cityNames.length" class="tabs" aria-label="Pilih kabupaten">
      <button
        v-for="name in cityNames"
        :key="name"
        type="button"
        :class="{ 'is-on': name === city }"
        :aria-pressed="name === city"
        @click="city = name"
      >
        {{ name }}
        <span v-if="data" :class="['dot', `dot--${classify(data.cities[name].forecast.p50.at(-1) as number, data.severity_thresholds).toLowerCase()}`]" aria-hidden="true"></span>
      </button>
    </nav>

    <div v-if="data && current" class="view30__grid">
      <div class="panel panel--chart">
        <div class="panel__head">
          <div>
            <h2>{{ city }}</h2>
            <span class="panel__meta">
              30 hari prediksi · titik acuan observasi {{ lastObs?.toFixed(2) }}
            </span>
          </div>
          <div class="panel__end">
            <span class="metric__label">P50 hari ke-30</span>
            <b>{{ endMedian?.toFixed(2) }}</b>
            <span :class="['chip', `chip--${endClass.toLowerCase()}`]">{{ CLASS_LABEL[endClass] }}</span>
          </div>
        </div>
        <Forecast30Chart :series="series" :baseline="lastObs" :bounds="data.severity_thresholds" />
      </div>

      <aside class="panel panel--side">
        <h2>Ringkasan horizon</h2>
        <ForecastMetrics :city="current" :bounds="data.severity_thresholds" />
        <p class="panel__foot">
          {{ endNote }} pada hari ke-30. Ambang: Waspada ≤ {{ data.severity_thresholds.moderate }},
          Siaga ≤ {{ data.severity_thresholds.severe }}, Awas ≤ {{ data.severity_thresholds.extreme }}.
        </p>
        <p class="panel__src">
          Checkpoint <code>{{ data.checkpoint }}</code> · observasi sampai {{ data.last_observed }}
        </p>
      </aside>
    </div>

    <p v-else-if="!error" class="notice" role="status">Memuat artefak prediksi 30 hari…</p>
  </section>
</template>