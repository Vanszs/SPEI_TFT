<script setup lang="ts">
import { computed } from 'vue';
import type { CityForecast, ForecastData } from '../data/forecast';
import { CLASS_LABEL, classify } from '../data/forecast';

const props = defineProps<{
  city: CityForecast;
  bounds: ForecastData['severity_thresholds'];
}>();

// Ambang dari model, bukan angka tambahan: 6 hari pertama / terakhir 5 hari.
const EARLY = 6;
const LATE = 5;

const p50 = computed(() => props.city.forecast.p50);
const worst = computed(() => props.city.forecast.p10);

const mean = (values: number[]) => values.reduce((s, v) => s + v, 0) / values.length;
const earlyMean = computed(() => mean(p50.value.slice(0, EARLY)));
const lateMean = computed(() => mean(p50.value.slice(-LATE)));

const dip = computed(() => p50.value.indexOf(Math.min(...p50.value)));
const rise = computed(() => p50.value.indexOf(Math.max(...p50.value)));

const classOf = (v: number) => classify(v, props.bounds);
const worstDay = computed(() => worst.value.indexOf(Math.min(...worst.value)));
const endClass = computed(() => classOf(lateMean.value));
const worstClass = computed(() => classOf(Math.min(...worst.value)));

const severeDays = computed(() => p50.value.filter((v) => v <= props.bounds.severe).length);
const moderateDays = computed(
  () => p50.value.filter((v) => v > props.bounds.severe && v <= props.bounds.moderate).length,
);

const trendLabel = computed(() => {
  const d = lateMean.value - earlyMean.value;
  if (d > 0.15) return 'Membaik';
  if (d < -0.15) return 'Mengering';
  return 'Datar';
});
const delta = computed(() => lateMean.value - earlyMean.value);
</script>

<template>
  <div class="metrics">
    <div class="metric">
      <span class="metric__label">Rerata 5 hari akhir (P50)</span>
      <span class="metric__value">{{ lateMean.toFixed(2) }}</span>
      <span :class="['chip', `chip--${endClass.toLowerCase()}`]">{{ CLASS_LABEL[endClass] }}</span>
    </div>
    <div class="metric">
      <span class="metric__label">Titik terbasah</span>
      <span class="metric__value">{{ p50[rise].toFixed(2) }}</span>
      <span class="metric__note">hari {{ rise + 1 }}</span>
    </div>
    <div class="metric">
      <span class="metric__label">Skenario kering (P10)</span>
      <span class="metric__value">{{ Math.min(...worst).toFixed(2) }}</span>
      <span :class="['chip', `chip--${worstClass.toLowerCase()}`]">{{ CLASS_LABEL[worstClass] }} · hari {{ worstDay + 1 }}</span>
    </div>
    <div class="metric">
      <span class="metric__label">Tren 30 hari</span>
      <span class="metric__value metric__value--small">{{ trendLabel }}</span>
      <span class="metric__note">Δ {{ delta >= 0 ? '+' : '−' }}{{ Math.abs(delta).toFixed(2) }} vs 6 hari awal</span>
    </div>
    <div class="metric">
      <span class="metric__label">Hari di bawah ambang</span>
      <span class="metric__value metric__value--small">{{ severeDays + moderateDays }}/30</span>
      <span class="metric__note">Siaga {{ severeDays }} · Waspada {{ moderateDays }}</span>
    </div>
    <div class="metric">
      <span class="metric__label">Depresi terdalam</span>
      <span class="metric__value metric__value--small">hari {{ dip + 1 }}</span>
      <span class="metric__note">P50 {{ p50[dip].toFixed(2) }}</span>
    </div>
  </div>
</template>