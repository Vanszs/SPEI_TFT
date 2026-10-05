<script setup lang="ts">
import { computed } from 'vue';
import type { DroughtSeverity, RegionPrediction } from '../types';

const props = withDefaults(
  defineProps<{
    region: RegionPrediction;
    horizon: number;
    featured?: boolean;
  }>(),
  { featured: false },
);

const emit = defineEmits<{ (e: 'select', region: RegionPrediction): void }>();

const severity: Record<DroughtSeverity, { label: string; chip: string }> = {
  NORMAL: { label: 'Normal', chip: 'chip chip--normal' },
  MODERATE: { label: 'Waspada', chip: 'chip chip--moderate' },
  SEVERE: { label: 'Siaga', chip: 'chip chip--severe' },
  EXTREME: { label: 'Awas', chip: 'chip chip--extreme' },
};

const meta = computed(() => severity[props.region.severity]);
const median = computed(() => props.region.speiForecast.q50);
const hasForecast = computed(() => Number.isFinite(median.value));
const current = computed(() => props.region.speiCurrent);
const lo = computed(() => props.region.speiForecast.q10);
const hi = computed(() => props.region.speiForecast.q90);
const delta = computed(() => (hasForecast.value ? median.value - current.value : null));
const range = computed(() => (hasForecast.value ? hi.value - lo.value : null));

// SPEI is plotted on a fixed -3..+1.5 axis so the band position is comparable card to card.
const AXIS_LO = -3;
const AXIS_HI = 1.5;
const pct = (v: number) => {
  const clamped = Math.max(AXIS_LO, Math.min(AXIS_HI, v));
  return ((clamped - AXIS_LO) / (AXIS_HI - AXIS_LO)) * 100;
};
const bandLeft = computed(() => pct(lo.value));
const bandWidth = computed(() => Math.max(1.5, pct(hi.value) - pct(lo.value)));
const markerLeft = computed(() => pct(median.value));
const currentLeft = computed(() => pct(current.value));

const fmt = (v: number) => (Number.isFinite(v) ? v.toFixed(2) : '—');
const sign = (v: number | null) => (v === null || v === 0 ? '' : v > 0 ? '+' : '−');
</script>

<template>
  <article
    :class="['pred-card', { 'pred-card--featured': featured }]"
    :aria-label="`Prediksi ${region.regencyName}`"
  >
    <header class="pred-card__head">
      <div class="pred-card__id">
        <h3>{{ region.regencyName }}</h3>
        <span class="pred-card__place">{{ region.province }}</span>
      </div>
      <span :class="meta.chip">{{ meta.label }}</span>
    </header>

    <div class="pred-card__readout">
      <div class="pred-read">
        <span class="pred-read__label">Sekarang</span>
        <span class="pred-read__value pred-read__value--muted">{{ fmt(current) }}</span>
      </div>
      <div class="pred-read pred-read--lead">
        <span class="pred-read__label">+{{ horizon }} bulan</span>
        <span class="pred-read__value">{{ fmt(median) }}</span>
      </div>
      <div class="pred-read">
        <span class="pred-read__label">Δ</span>
        <span class="pred-read__value pred-read__value--muted">
          {{ delta === null ? '—' : sign(delta) + Math.abs(delta).toFixed(2) }}
        </span>
      </div>
    </div>

    <div
      class="pred-band"
      role="img"
      :aria-label="`Rentang kemungkinan 80 persen ${fmt(lo)} sampai ${fmt(hi)}`"
    >
      <span class="pred-band__track" aria-hidden="true"></span>
      <span
        v-if="hasForecast"
        class="pred-band__range"
        :style="{ left: bandLeft + '%', width: bandWidth + '%' }"
        aria-hidden="true"
      ></span>
      <span class="pred-band__now" :style="{ left: currentLeft + '%' }" aria-hidden="true"></span>
      <span
        v-if="hasForecast"
        class="pred-band__median"
        :style="{ left: markerLeft + '%' }"
        aria-hidden="true"
      ></span>
    </div>

    <dl class="pred-card__foot">
      <div><dt>P10–P90</dt><dd>{{ fmt(lo) }} … {{ fmt(hi) }}</dd></div>
      <div><dt>Lebar</dt><dd>{{ range === null ? '—' : range.toFixed(2) }}</dd></div>
    </dl>

    <button class="pred-card__open" type="button" @click="emit('select', region)">
      Buka rincian {{ region.regencyName.replace(/^Kab\.\s*/i, '') }}
    </button>
  </article>
</template>
