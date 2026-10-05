<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import type { DayPoint, ForecastData } from '../data/forecast';
import { CLASS_LABEL, classify, dayLabel } from '../data/forecast';

const props = defineProps<{
  series: DayPoint[];
  baseline: number | null;
  bounds: ForecastData['severity_thresholds'];
}>();

// viewBox lebih sempit di layar kecil: rasio tetap 720:240 membuat grafik
// hanya ~98px tinggi pada 360px. 420:260 memberi ruang vertikal yang layak.
const compact = ref(false);
let mq: MediaQueryList | null = null;
const onMq = (e: MediaQueryListEvent) => (compact.value = e.matches);
onMounted(() => {
  mq = window.matchMedia('(max-width: 760px)');
  compact.value = mq.matches;
  mq.addEventListener('change', onMq);
});
onUnmounted(() => mq?.removeEventListener('change', onMq));

const W = computed(() => (compact.value ? 420 : 720));
const H = computed(() => (compact.value ? 260 : 240));
const M = computed(() => ({ top: 18, right: 12, bottom: 30, left: 38 }));
const plotW = computed(() => W.value - M.value.left - M.value.right);
const plotH = computed(() => H.value - M.value.top - M.value.bottom);
// Domain mengikuti data, bukan tetap -2.5..1.5: kalau semua nilai positif,
// pita P10-P90 hanya jadi sliver tipis dan grafik tak terbaca.
// Ambang kekeringan hanya digambar bila memang jatuh di dalam domain.
const domain = computed(() => {
  const vals = props.series.flatMap((p) => [p.p10 as number, p.p90 as number]).filter(Number.isFinite);
  if (!vals.length) return { min: -1, max: 1 };
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const pad = Math.max(0.15, (hi - lo) * 0.35);
  let min = lo - pad;
  let max = hi + pad;
  // Sertakan ambang terdekat bila hanya sedikit di luar domain, supaya konteks kering tetap ada.
  const nearest = [props.bounds.moderate, props.bounds.severe, props.bounds.extreme].filter((t) => t <= hi)
    .sort((a, b) => b - a)[0];
  if (nearest !== undefined && nearest > min - pad * 2) min = nearest - pad * 0.6;
  return { min, max };
});

const hover = ref<number | null>(null);

const x = (i: number) => M.value.left + (i / Math.max(1, props.series.length - 1)) * plotW.value;
const y = (v: number) => {
  const { min, max } = domain.value;
  const clamped = Math.max(min, Math.min(max, v));
  return M.value.top + ((max - clamped) / (max - min)) * plotH.value;
};

// Tick per 5 hari + hari terakhir: data hanya 30 hari sehingga tick berbasis
// tanggal 1 tidak akan pernah muncul.
const dateTicks = computed(() =>
  props.series
    .map((p, i) => ({ i, label: p.monthLabel }))
    .filter((t) => t.i % 5 === 0 || t.i === props.series.length - 1),
);

const paths = computed(() => {
  const s = props.series;
  const line = (pick: (p: DayPoint) => number | undefined) =>
    s
      .map((p, i) => ({ v: pick(p), i }))
      .filter((a) => a.v !== undefined)
      .map((a, k) => `${k === 0 ? 'M' : 'L'}${x(a.i).toFixed(1)},${y(a.v as number).toFixed(1)}`)
      .join(' ');

  const up = s.map((p, i) => `${x(i).toFixed(1)},${y(p.p90 as number).toFixed(1)}`);
  const down = [...s].reverse().map((p, k) => `${x(s.length - 1 - k).toFixed(1)},${y(p.p10 as number).toFixed(1)}`);

  return {
    med: line((p) => p.p50),
    p10: line((p) => p.p10),
    p90: line((p) => p.p90),
    band: up.length ? `M${up.join(' L')} L${down.join(' L')} Z` : '',
    base: props.baseline === null ? null : y(props.baseline),
  };
});

const thresholds = computed(() => {
  const { min } = domain.value;
  return [
    { v: props.bounds.moderate, label: 'Waspada' },
    { v: props.bounds.severe, label: 'Siaga' },
  ].filter((t) => t.v >= min);
});
const yTicks = computed(() => {
  const { min, max } = domain.value;
  const span = max - min;
  const raw = span / 4;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((v) => v >= raw) ?? mag * 10;
  const decimals = step < 0.5 ? 2 : 1;
  const ticks: { v: number; label: string }[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) {
    ticks.push({ v: Number(v.toFixed(2)), label: v.toFixed(decimals) });
  }
  return ticks;
});
const showTable = ref(false);

const active = computed(() => (hover.value === null ? null : props.series[hover.value]));
const activeClass = computed(() => (active.value ? classify(active.value.p50 as number, props.bounds) : 'NORMAL'));

function pickFromEvent(event: MouseEvent) {
  const rect = (event.currentTarget as SVGElement).getBoundingClientRect();
  const px = ((event.clientX - rect.left) / rect.width) * W.value;
  const raw = ((px - M.value.left) / plotW.value) * (props.series.length - 1);
  hover.value = Math.max(0, Math.min(props.series.length - 1, Math.round(raw)));
}
function step(delta: number) {
  const start = hover.value ?? 0;
  hover.value = Math.max(0, Math.min(props.series.length - 1, start + delta));
}
</script>

<template>
  <div class="chart">
    <div class="chart__legend">
      <span class="lg lg--band">Rentang P10–P90 (80%)</span>
      <span class="lg lg--med">Median P50</span>
      <span class="lg lg--edge">Batas P10 / P90</span>
      <span v-if="baseline !== null" class="lg lg--base">Observasi terakhir {{ baseline.toFixed(2) }}</span>
    </div>

    <div class="chart__stage">
      <svg
        :viewBox="`0 0 ${W} ${H}`"
        class="chart__svg"
        tabindex="0"
        role="img"
        aria-label="Prediksi SPEI 30 hari ke depan. Gunakan tombol panah kiri dan kanan untuk membaca nilai harian."
        @mousemove="pickFromEvent"
        @mouseleave="hover = null"
        @focus="hover = hover ?? 0"
        @blur="hover = null"
        @keydown.left.prevent="step(-1)"
        @keydown.right.prevent="step(1)"
        @keydown.home.prevent="hover = 0"
        @keydown.end.prevent="hover = series.length - 1"
      >
        <g class="grid">
          <line v-for="t in yTicks" :key="t.v" :x1="M.left" :x2="W - M.right" :y1="y(t.v)" :y2="y(t.v)" />
        </g>

        <line v-if="paths.base !== null" :x1="M.left" :x2="W - M.right" :y1="paths.base" :y2="paths.base" class="base" />

        <path :d="paths.band" class="band" />
        <path :d="paths.p90" class="edge" />
        <path :d="paths.p10" class="edge" />
        <path :d="paths.med" class="med" />

        <g class="thresh">
          <template v-for="t in thresholds" :key="t.label">
            <line :x1="M.left" :x2="W - M.right" :y1="y(t.v)" :y2="y(t.v)" />
            <text :x="M.left + 5" :y="y(t.v) - 4">{{ t.label }} ≤ {{ t.v.toFixed(1) }}</text>
          </template>
        </g>

        <g class="axis-y">
          <text v-for="t in yTicks" :key="t.v" :x="M.left - 7" :y="y(t.v) + 3">{{ t.label }}</text>
        </g>
        <g class="axis-x">
          <text v-for="(t, k) in dateTicks" :key="t.i" :x="x(t.i)" :y="H - 10" :style="{ textAnchor: k === dateTicks.length - 1 ? 'end' : 'middle' }">{{ t.label }}</text>
        </g>

        <g v-if="active && hover !== null">
          <line :x1="x(hover)" :x2="x(hover)" :y1="M.top" :y2="M.top + plotH" class="cursor" />
          <circle :cx="x(hover)" :cy="y(active.p50 as number)" r="3.4" class="dot-med" />
        </g>
      </svg>

      <div class="readout" aria-live="polite">
        <div v-if="active" class="readout__body">
          <div class="readout__top">
            <span class="readout__date">{{ dayLabel(active.date) }}</span>
            <span :class="['chip', `chip--${activeClass.toLowerCase()}`]">{{ CLASS_LABEL[activeClass] }}</span>
          </div>
          <span class="readout__kind">Hari ke-{{ hover! + 1 }}</span>
          <dl class="readout__grid">
            <div><dt>P50</dt><dd>{{ (active.p50 as number).toFixed(2) }}</dd></div>
            <div><dt>P10</dt><dd>{{ (active.p10 as number).toFixed(2) }}</dd></div>
            <div><dt>P90</dt><dd>{{ (active.p90 as number).toFixed(2) }}</dd></div>
            <div><dt>Lebar 80%</dt><dd>{{ ((active.p90 as number) - (active.p10 as number)).toFixed(2) }}</dd></div>
          </dl>
        </div>
        <p v-else class="readout__hint">Arahkan kursor atau fokuskan grafik, lalu pakai tombol panah untuk membaca tiap hari.</p>
      </div>
    </div>

    <button class="disclose" type="button" :aria-expanded="showTable" aria-controls="chart-table-30d" @click="showTable = !showTable">
      {{ showTable ? 'Sembunyikan tabel 30 hari' : 'Tampilkan tabel 30 hari' }}
    </button>

    <div v-if="showTable" id="chart-table-30d" class="chart__table">
      <table>
        <caption>Nilai harian prediksi 30 hari: P50 dan rentang 80%</caption>
        <thead><tr><th scope="col">Hari</th><th scope="col">Tanggal</th><th scope="col">P10</th><th scope="col">P50</th><th scope="col">P90</th></tr></thead>
        <tbody>
          <tr v-for="(p, i) in series" :key="p.date">
            <th scope="row">{{ i + 1 }}</th>
            <td>{{ p.date.slice(5) }}</td>
            <td>{{ (p.p10 as number).toFixed(2) }}</td>
            <td>{{ (p.p50 as number).toFixed(2) }}</td>
            <td>{{ (p.p90 as number).toFixed(2) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>