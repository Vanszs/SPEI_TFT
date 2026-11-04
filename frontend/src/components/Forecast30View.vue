<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { RefreshCw } from 'lucide-vue-next';
import Forecast30Chart from './Forecast30Chart.vue';
import ForecastMetrics from './ForecastMetrics.vue';
import ReadingGuide from './ReadingGuide.vue';
import ForecastHistory from './ForecastHistory.vue';
import {
  CLASS_LABEL,
  classify,
  lastObserved,
  loadForecast30d,
  monthTitle,
  toForecastSeries,
  type ForecastData,
} from '../data/forecast';

const props = defineProps<{ focusCity?: string | null }>();

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
      const preferred = props.focusCity && d.cities[props.focusCity] ? props.focusCity : null;
      city.value = preferred ?? (city.value && d.cities[city.value] ? city.value : Object.keys(d.cities)[0]);
    })
    .catch((e: unknown) => {
      if ((e as Error).name !== 'AbortError') error.value = (e as Error).message;
    });
}

onMounted(load);
onUnmounted(() => controller?.abort());
watch(() => props.focusCity, (value) => {
  if (value && data.value?.cities[value]) city.value = value;
});

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

// Jendela prakiraan yang sudah lewat bukan lagi "30 hari ke depan".
// Siklus bulanan: arsip hanya jika anchor artefak lebih lama dari siklus
// yang seharusnya (tanggal 1 bulan lalu). Jendela yang sudah lewat itu normal.
const isArchived = computed(() => {
  if (!data.value?.anchor) return false;
  const now = new Date();
  const year = now.getMonth() === 0 ? now.getFullYear() - 1 : now.getFullYear();
  const month = now.getMonth() === 0 ? 11 : now.getMonth() - 1;
  const expected = new Date(year, month, 1);
  return new Date(`${data.value.anchor}T00:00:00`) < expected;
});
const endClass = computed(() =>
  data.value && endMedian.value !== null ? classify(endMedian.value, data.value.severity_thresholds) : 'NORMAL',
);
const endNote = computed(() => {
  if (!data.value || !current.value) return '';
  const last = current.value.forecast.p50.at(-1) as number;
  return `Status hari ke-30: ${CLASS_LABEL[classify(last, data.value.severity_thresholds)]}`;
});
</script>

<template>
  <section id="prediksi-30" class="view30" aria-labelledby="prediksi-30-title">
    <div v-if="error" class="notice notice--error" role="alert">{{ error }}</div>
    <div v-else-if="isArchived && data" class="notice notice--error" role="alert">
      Siklus prakiraan ini tertinggal dari jadwal bulanan. Data berhenti {{ data.last_observed }}. Jalankan pembaruan agar kembali ke siklus berjalan.
    </div>

    <ReadingGuide compact />

    <header class="view30__head">
      <div>
        <span class="eyebrow">Prakiraan bulanan · lag 1 bulan</span>
        <h1 id="prediksi-30-title">{{ isArchived ? 'Arsip prakiraan SPEI' : 'Prakiraan SPEI harian' }} hingga {{ monthSpan }}.</h1>
        <p>
          Keluaran Temporal Fusion Transformer dengan encoder 90 hari. Rentang P10–P90 adalah
          ketidakpastian model, bukan peringatan resmi.
        </p>
      </div>
      <div v-if="data" class="view30__aside">
        <span :class="['freshness', { 'freshness--stale': isArchived }]">
          <span class="freshness__dot" aria-hidden="true"></span>
          Data s/d {{ data.last_observed }} · siklus {{ data.anchor ? monthTitle(data.anchor) : '—' }}{{ isArchived ? ' · perlu pembaruan' : '' }}
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
          {{ endNote }}. Ambang: Waspada ≤ {{ data.severity_thresholds.moderate }},
          Siaga ≤ {{ data.severity_thresholds.severe }}, Awas ≤ {{ data.severity_thresholds.extreme }}.
        </p>
        <p class="panel__src">
          Checkpoint <code>{{ data.checkpoint }}</code> · observasi sampai {{ data.last_observed }}
        </p>
      </aside>
    </div>

    <ForecastHistory v-if="current?.history?.length" :windows="current.history" />

    <p v-if="!data && !error" class="notice" role="status">Memuat artefak prediksi 30 hari…</p>
  </section>
</template>
