<script lang="ts">
import type { RegionPrediction } from '../types';

export interface FanChartDataPoint {
  month: string;
  isForecast: boolean;
  actual?: number;
  q10?: number;
  q50?: number;
  q90?: number;
  q10_q50_diff?: number;
  q50_q90_diff?: number;
}

// Generate data combining 6M historical trajectory + +1M..+12M quantile forecast
export function generateFanChartData(region: RegionPrediction, horizonsCount = 12): FanChartDataPoint[] {
  const data: FanChartDataPoint[] = [];

  // Historical points
  region.historicalSpei.forEach((h) => {
    data.push({
      month: h.month,
      isForecast: false,
      actual: h.actual,
    });
  });

  const lastHist = region.historicalSpei[region.historicalSpei.length - 1];
  const lastActual = lastHist ? lastHist.actual : region.speiCurrent;

  // Seamless connection at forecast start (Horizon +0)
  // Stack diffs = 0 at start point
  data[data.length - 1] = {
    ...data[data.length - 1],
    q10: lastActual,
    q50: lastActual,
    q90: lastActual,
    q10_q50_diff: 0,
    q50_q90_diff: 0,
  };

  // Generate +1M to +12M horizons
  const forecastMonths = ['Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec', 'Jan+1', 'Feb+1', 'Mar+1', 'Apr+1', 'May+1', 'Jun+1'];

  const targetQ10 = region.speiForecast.q10;
  const targetQ50 = region.speiForecast.q50;
  const targetQ90 = region.speiForecast.q90;

  for (let i = 1; i <= horizonsCount; i++) {
    const monthName = forecastMonths[(i - 1) % forecastMonths.length];

    // Fan uncertainty widens as forecast horizon extends
    const factor = Math.sqrt(i / 3);
    const q50Val = Number((lastActual + (targetQ50 - lastActual) * (i / 3)).toFixed(2));
    const q10Val = Number((q50Val + (targetQ10 - targetQ50) * factor).toFixed(2));
    const q90Val = Number((q50Val + (targetQ90 - targetQ50) * factor).toFixed(2));

    data.push({
      month: `${monthName} (+${i}M)`,
      isForecast: true,
      q10: q10Val,
      q50: q50Val,
      q90: q90Val,
      q10_q50_diff: Number((q50Val - q10Val).toFixed(2)),
      q50_q90_diff: Number((q90Val - q50Val).toFixed(2)),
    });
  }

  return data;
}
</script>

<script setup lang="ts">
import { ref, computed } from 'vue';

interface TFTFanChartProps {
  region: RegionPrediction;
  selectedHorizon?: number; // 1, 3, 6, or 12
  className?: string;
}

const props = withDefaults(defineProps<TFTFanChartProps>(), {
  selectedHorizon: 3,
  className: '',
});

const emit = defineEmits<{
  (e: 'horizonChange', horizon: number): void;
}>();

const showUncertaintyBands = ref(true);
const chartData = computed(() => generateFanChartData(props.region, 12));

const activeHorizonPoint = computed(() =>
  chartData.value.find((d) => d.month.includes(`(+${props.selectedHorizon}M)`))
);

const handleHorizonChange = (h: number) => {
  emit('horizonChange', h);
};

// SVG Coordinate Space Constants
const width = 680;
const height = 240;
const marginLeft = 38;
const marginRight = 92;
const marginTop = 16;
const marginBottom = 34;
const plotWidth = width - marginLeft - marginRight; // 550
const plotHeight = height - marginTop - marginBottom; // 190

const yMin = -3.0;
const yMax = 1.5;
const ySpan = yMax - yMin;

const getY = (val: number): number => {
  const clamped = Math.max(yMin, Math.min(yMax, val));
  return marginTop + plotHeight * ((yMax - clamped) / ySpan);
};

const getX = (index: number, count: number): number => {
  return marginLeft + (index / Math.max(1, count - 1)) * plotWidth;
};

const yTicks = [-2.5, -2.0, -1.5, -0.5, 0, 0.5, 1.0];

const lastHistIndex = computed(() => props.region.historicalSpei.length - 1);

interface PointCoords extends FanChartDataPoint {
  index: number;
  x: number;
  yActual?: number;
  yQ10?: number;
  yQ50?: number;
  yQ90?: number;
}

const points = computed<PointCoords[]>(() => {
  const data = chartData.value;
  const count = data.length;
  return data.map((d, i) => ({
    ...d,
    index: i,
    x: getX(i, count),
    yActual: d.actual !== undefined ? getY(d.actual) : undefined,
    yQ10: d.q10 !== undefined ? getY(d.q10) : undefined,
    yQ50: d.q50 !== undefined ? getY(d.q50) : undefined,
    yQ90: d.q90 !== undefined ? getY(d.q90) : undefined,
  }));
});

const histPoints = computed(() => {
  return points.value.slice(0, lastHistIndex.value + 1).filter((p) => p.yActual !== undefined);
});

const actualPath = computed(() => {
  const pts = points.value.slice(0, lastHistIndex.value + 1);
  if (pts.length === 0) return '';
  return pts.map((p, idx) => `${idx === 0 ? 'M' : 'L'} ${p.x.toFixed(1)},${(p.yActual ?? getY(0)).toFixed(1)}`).join(' ');
});

const forecastPoints = computed(() => {
  return points.value.slice(Math.max(0, lastHistIndex.value));
});

// Lower Fan Band: q10 to q50
const q10q50BandPath = computed(() => {
  const fPts = forecastPoints.value;
  if (fPts.length < 2) return '';
  const top = fPts.map((p, idx) => `${idx === 0 ? 'M' : 'L'} ${p.x.toFixed(1)},${(p.yQ50 ?? getY(0)).toFixed(1)}`);
  const bottom = [...fPts].reverse().map((p) => `L ${p.x.toFixed(1)},${(p.yQ10 ?? getY(0)).toFixed(1)}`);
  return `${top.join(' ')} ${bottom.join(' ')} Z`;
});

// Upper Fan Band: q50 to q90
const q50q90BandPath = computed(() => {
  const fPts = forecastPoints.value;
  if (fPts.length < 2) return '';
  const top = fPts.map((p, idx) => `${idx === 0 ? 'M' : 'L'} ${p.x.toFixed(1)},${(p.yQ90 ?? getY(0)).toFixed(1)}`);
  const bottom = [...fPts].reverse().map((p) => `L ${p.x.toFixed(1)},${(p.yQ50 ?? getY(0)).toFixed(1)}`);
  return `${top.join(' ')} ${bottom.join(' ')} Z`;
});

const q50Path = computed(() => {
  const fPts = forecastPoints.value;
  if (fPts.length < 2) return '';
  return fPts.map((p, idx) => `${idx === 0 ? 'M' : 'L'} ${p.x.toFixed(1)},${(p.yQ50 ?? getY(0)).toFixed(1)}`).join(' ');
});

const q10Path = computed(() => {
  const fPts = forecastPoints.value;
  if (fPts.length < 2) return '';
  return fPts.map((p, idx) => `${idx === 0 ? 'M' : 'L'} ${p.x.toFixed(1)},${(p.yQ10 ?? getY(0)).toFixed(1)}`).join(' ');
});

const q90Path = computed(() => {
  const fPts = forecastPoints.value;
  if (fPts.length < 2) return '';
  return fPts.map((p, idx) => `${idx === 0 ? 'M' : 'L'} ${p.x.toFixed(1)},${(p.yQ90 ?? getY(0)).toFixed(1)}`).join(' ');
});

const activeHorizonCoords = computed(() =>
  points.value.find((d) => d.month.includes(`(+${props.selectedHorizon}M)`))
);

// Tooltip State
const svgContainerRef = ref<HTMLDivElement | null>(null);
const svgRef = ref<SVGSVGElement | null>(null);
const hoveredIndex = ref<number | null>(null);
const tooltipPos = ref({ x: 0, y: 0 });

const hoveredPoint = computed(() => {
  if (hoveredIndex.value === null) return null;
  return chartData.value[hoveredIndex.value] ?? null;
});

const handleMouseMove = (e: MouseEvent) => {
  if (!svgRef.value || !svgContainerRef.value) return;
  const svgRect = svgRef.value.getBoundingClientRect();
  const containerRect = svgContainerRef.value.getBoundingClientRect();

  const svgX = ((e.clientX - svgRect.left) / svgRect.width) * width;

  let closestIdx = 0;
  let minDiff = Infinity;
  points.value.forEach((pt, idx) => {
    const diff = Math.abs(pt.x - svgX);
    if (diff < minDiff) {
      minDiff = diff;
      closestIdx = idx;
    }
  });

  hoveredIndex.value = closestIdx;
  tooltipPos.value = {
    x: e.clientX - containerRect.left,
    y: e.clientY - containerRect.top,
  };
};

const handleMouseLeave = () => {
  hoveredIndex.value = null;
};

const getSpeiCategory = (val?: number) => {
  if (val === undefined) return { label: 'N/A', color: 'text-[var(--muted)]' };
  if (val <= -2.0) return { label: 'Kekeringan ekstrem', color: 'text-[var(--red)]' };
  if (val <= -1.5) return { label: 'Kekeringan parah', color: 'text-[#b45b2c]' };
  if (val <= -0.5) return { label: 'Kekeringan sedang', color: 'text-[var(--amber)]' };
  if (val < 0.5) return { label: 'Normal', color: 'text-[var(--green)]' };
  return { label: 'Lebih basah dari normal', color: 'text-[var(--blue)]' };
};

const hoveredSpeiStatus = computed(() => {
  if (!hoveredPoint.value) return { label: '', color: '' };
  return getSpeiCategory(hoveredPoint.value.isForecast ? hoveredPoint.value.q50 : hoveredPoint.value.actual);
});
</script>

<template>
  <div :class="`bg-[#f3f6f2] border-[var(--line)] rounded-lg p-5 flex flex-col space-y-4 ${className}`">
    <!-- Header & Controls Chrome -->
    <div class="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--line)] pb-3">
      <div>
        <div class="flex items-center space-x-2">
          <span class="w-2 h-2 rounded-full bg-[var(--green)] animate-pulse"></span>
          <h3 class="text-xs font-mono font-semibold uppercase tracking-wider text-gray-200">
            Prediksi SPEI dengan rentang kemungkinan ({{ region.regencyName }})
          </h3>
        </div>
        <p class="text-[11px] font-mono text-gray-400 mt-0.5">
          Garis putus-putus = nilai tengah; pita = rentang kemungkinan 80%.
        </p>
      </div>

      <div class="flex items-center space-x-2">
        <!-- Horizon Selection Buttons -->
        <div class="flex items-center bg-gray-900 border-[var(--line)] rounded p-0.5">
          <button
            v-for="h in [1, 3, 6, 12]"
            :key="h"
            @click="handleHorizonChange(h)"
            :class="`px-2 py-0.5 text-[11px] font-mono rounded transition-colors ${
              selectedHorizon === h
                ? 'bg-[var(--blue-soft)] text-[var(--blue)] border border-[var(--blue)] font-semibold'
                : 'text-gray-400 hover:text-gray-200'
            }`"
          >
            +{{ h }}M
          </button>
        </div>

        <!-- Toggle Band Visibility -->
        <button
          @click="showUncertaintyBands = !showUncertaintyBands"
          :class="`px-2 py-1 text-[10px] font-mono rounded border transition-colors ${
            showUncertaintyBands
              ? 'bg-gray-800 text-gray-200 border-gray-700'
              : 'bg-gray-900 text-gray-500 var(--line) line-through'
          }`"
        >
          PITA
        </button>
      </div>
    </div>

    <!-- Main Fan-Chart Visual Canvas (Hand-rolled Plain SVG) -->
    <div
      ref="svgContainerRef"
      class="h-64 w-full bg-[var(--surface)] border-[var(--line)] rounded p-2 relative select-none"
    >
      <svg
        ref="svgRef"
        class="w-full h-full block"
        :viewBox="`0 0 ${width} ${height}`"
        preserveAspectRatio="xMidYMid meet"
        @mousemove="handleMouseMove"
        @mouseleave="handleMouseLeave"
      >
        <defs>
          <!-- Outer 80% CI Shading (q10 to q50) -->
          <linearGradient id="fanOuterBand" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="#56708a" stop-opacity="0.05" />
            <stop offset="100%" stop-color="#56708a" stop-opacity="0.25" />
          </linearGradient>
          <!-- Inner 50% / Median Shading (q50 to q90) -->
          <linearGradient id="fanInnerBand" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="#4c7a78" stop-opacity="0.1" />
            <stop offset="100%" stop-color="#4c7a78" stop-opacity="0.4" />
          </linearGradient>
        </defs>

        <!-- Cartesian Grid (Horizontal lines) -->
        <g class="cartesian-grid">
          <line
            v-for="tick in yTicks"
            :key="`grid-${tick}`"
            :x1="marginLeft"
            :y1="getY(tick)"
            :x2="marginLeft + plotWidth"
            :y2="getY(tick)"
            stroke="#d4dbd3"
            stroke-dasharray="3 3"
            stroke-width="1"
          />
        </g>

        <!-- Y-Axis labels & axis line -->
        <g class="y-axis font-mono text-[9px]">
          <line
            :x1="marginLeft"
            :y1="marginTop"
            :x2="marginLeft"
            :y2="marginTop + plotHeight"
            stroke="#374151"
            stroke-width="1"
          />
          <text
            v-for="tick in yTicks"
            :key="`ytick-${tick}`"
            :x="marginLeft - 5"
            :y="getY(tick) + 3"
            text-anchor="end"
            fill="#6b7280"
            font-size="9"
            font-family="monospace"
          >
            {{ tick.toFixed(1) }}
          </text>
        </g>

        <!-- X-Axis line & labels -->
        <g class="x-axis font-mono">
          <line
            :x1="marginLeft"
            :y1="marginTop + plotHeight"
            :x2="marginLeft + plotWidth"
            :y2="marginTop + plotHeight"
            stroke="#374151"
            stroke-width="1"
          />
          <text
            v-for="pt in points"
            :key="`xtick-${pt.index}`"
            :x="pt.x"
            :y="marginTop + plotHeight + 11"
            :transform="`rotate(-32 ${pt.x} ${marginTop + plotHeight + 11})`"
            text-anchor="end"
            fill="#6b7280"
            font-size="8"
            font-family="monospace"
          >
            {{ pt.month }}
          </text>
        </g>

        <!-- Threshold Reference Lines -->
        <g class="reference-lines">
          <!-- y = 0 Baseline -->
          <line
            :x1="marginLeft"
            :y1="getY(0)"
            :x2="marginLeft + plotWidth"
            :y2="getY(0)"
            stroke="#9aa8a0"
            stroke-dasharray="2 2"
            stroke-width="1"
          />

          <!-- MODERATE (-0.5) -->
          <line
            :x1="marginLeft"
            :y1="getY(-0.5)"
            :x2="marginLeft + plotWidth"
            :y2="getY(-0.5)"
            stroke="#9a5b00"
            stroke-dasharray="4 4"
            stroke-width="1"
          />
          <text
            :x="marginLeft + plotWidth + 4"
            :y="getY(-0.5) + 3"
            fill="#9a5b00"
            font-size="9"
            font-family="monospace"
          >
            MODERATE (-0.5)
          </text>

          <!-- SEVERE (-1.5) -->
          <line
            :x1="marginLeft"
            :y1="getY(-1.5)"
            :x2="marginLeft + plotWidth"
            :y2="getY(-1.5)"
            stroke="#b45b2c"
            stroke-dasharray="4 4"
            stroke-width="1"
          />
          <text
            :x="marginLeft + plotWidth + 4"
            :y="getY(-1.5) + 3"
            fill="#b45b2c"
            font-size="9"
            font-family="monospace"
          >
            SEVERE (-1.5)
          </text>

          <!-- EXTREME (-2.0) -->
          <line
            :x1="marginLeft"
            :y1="getY(-2.0)"
            :x2="marginLeft + plotWidth"
            :y2="getY(-2.0)"
            stroke="#a33d2e"
            stroke-dasharray="4 4"
            stroke-width="1"
          />
          <text
            :x="marginLeft + plotWidth + 4"
            :y="getY(-2.0) + 3"
            fill="#a33d2e"
            font-size="9"
            font-family="monospace"
          >
            EXTREME (-2.0)
          </text>
        </g>

        <!-- Selected Horizon Highlight Line -->
        <g v-if="activeHorizonCoords" class="active-horizon-highlight">
          <line
            :x1="activeHorizonCoords.x"
            :y1="marginTop"
            :x2="activeHorizonCoords.x"
            :y2="marginTop + plotHeight"
            stroke="#56708a"
            stroke-width="1.5"
            stroke-dasharray="2 2"
          />
          <circle
            v-if="activeHorizonCoords.yQ50 !== undefined"
            :cx="activeHorizonCoords.x"
            :cy="activeHorizonCoords.yQ50"
            r="4"
            fill="#9a5b00"
          />
        </g>

        <!-- Uncertainty Fan Bands (Filled Polygons) -->
        <g v-if="showUncertaintyBands" class="fan-bands">
          <!-- q10 to q50 Band -->
          <path
            :d="q10q50BandPath"
            fill="url(#fanOuterBand)"
            stroke="none"
          />
          <!-- q50 to q90 Band -->
          <path
            :d="q50q90BandPath"
            fill="url(#fanInnerBand)"
            stroke="none"
          />
          <!-- q10 Boundary Line -->
          <path
            :d="q10Path"
            fill="none"
            stroke="#a33d2e"
            stroke-width="1"
            stroke-dasharray="2 2"
          />
          <!-- q90 Boundary Line -->
          <path
            :d="q90Path"
            fill="none"
            stroke="#0b6f68"
            stroke-width="1"
            stroke-dasharray="2 2"
          />
        </g>

        <!-- Quantile q50 Median Forecast Line -->
        <path
          :d="q50Path"
          fill="none"
          stroke="#9a5b00"
          stroke-width="2"
          stroke-dasharray="4 4"
        />

        <!-- Historical Actual Line & Dots -->
        <g class="historical-actual">
          <path
            :d="actualPath"
            fill="none"
            stroke="#56708a"
            stroke-width="2"
          />
          <circle
            v-for="pt in histPoints"
            :key="`hist-dot-${pt.index}`"
            :cx="pt.x"
            :cy="pt.yActual"
            r="3"
            fill="#56708a"
          />
        </g>

        <!-- Hovered Point Indicator Line -->
        <g v-if="hoveredIndex !== null && points[hoveredIndex]" class="hover-indicator">
          <line
            :x1="points[hoveredIndex].x"
            :y1="marginTop"
            :x2="points[hoveredIndex].x"
            :y2="marginTop + plotHeight"
            stroke="#56708a"
            stroke-width="1"
            stroke-dasharray="3 3"
            opacity="0.8"
          />
          <circle
            v-if="points[hoveredIndex].isForecast && points[hoveredIndex].yQ50 !== undefined"
            :cx="points[hoveredIndex].x"
            :cy="points[hoveredIndex].yQ50"
            r="4"
            fill="#9a5b00"
          />
          <circle
            v-else-if="!points[hoveredIndex].isForecast && points[hoveredIndex].yActual !== undefined"
            :cx="points[hoveredIndex].x"
            :cy="points[hoveredIndex].yActual"
            r="4"
            fill="#56708a"
          />
        </g>
      </svg>

      <!-- Hover Tooltip -->
      <div
        v-if="hoveredPoint"
        class="absolute z-20 pointer-events-none bg-[var(--surface)]/95 border border-[var(--line)] p-3 rounded-md shadow-lg backdrop-blur font-mono text-xs max-w-xs space-y-2 transition-all duration-75"
        :style="{
          left: `${Math.min(Math.max(tooltipPos.x - 100, 10), 420)}px`,
          top: `${Math.max(tooltipPos.y - 130, 8)}px`,
        }"
      >
        <div class="flex items-center justify-between border-b border-[var(--line)] pb-1.5 gap-2">
          <span class="font-bold text-[var(--ink)]">{{ hoveredPoint.month }}</span>
          <span
            :class="`text-[10px] px-1.5 py-0.5 rounded border ${
              hoveredPoint.isForecast
                ? 'bg-[var(--soft-green)] text-[var(--green)] border-[var(--green)]'
                : 'bg-[#f0f2ee] text-[var(--muted)] border-[var(--line)]'
            }`"
          >
            {{ hoveredPoint.isForecast ? 'HASIL EVALUASI MODEL' : 'OBSERVASI' }}
          </span>
        </div>

        <div class="space-y-1">
          <div class="text-[11px] font-semibold flex justify-between gap-2">
            <span class="text-[var(--muted)]">Kondisi:</span>
            <span :class="hoveredSpeiStatus.color">{{ hoveredSpeiStatus.label }}</span>
          </div>

          <div
            v-if="!hoveredPoint.isForecast && hoveredPoint.actual !== undefined"
            class="flex justify-between text-[var(--ink)]"
          >
            <span class="text-[var(--muted)]">SPEI teramati:</span>
            <span class="font-bold text-[var(--blue)]">{{ hoveredPoint.actual.toFixed(2) }}</span>
          </div>

          <template v-if="hoveredPoint.isForecast">
            <div class="flex justify-between text-[var(--green)]">
              <span>q0.90 (batas lebih basah):</span>
              <span class="font-bold">{{ hoveredPoint.q90?.toFixed(2) }}</span>
            </div>
            <div class="flex justify-between text-[var(--blue)] font-semibold bg-[var(--blue-soft)] px-1 py-0.5 rounded">
              <span>q0.50 (nilai tengah):</span>
              <span class="font-bold">{{ hoveredPoint.q50?.toFixed(2) }}</span>
            </div>
            <div class="flex justify-between text-[var(--red)]">
              <span>q0.10 (batas lebih kering):</span>
              <span class="font-bold">{{ hoveredPoint.q10?.toFixed(2) }}</span>
            </div>
            <div
              v-if="hoveredPoint.q90 !== undefined && hoveredPoint.q10 !== undefined"
              class="flex justify-between text-[10px] text-[var(--muted)] pt-1 border-t border-[var(--line)]"
            >
              <span>Rentang kemungkinan 80%:</span>
              <span>{{ (hoveredPoint.q90 - hoveredPoint.q10).toFixed(2) }} ΔSPEI</span>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- Legend & Metric Summary -->
    <div class="flex flex-wrap items-center justify-between text-[11px] font-mono text-gray-400 gap-2 bg-[#ffffff] p-2.5 rounded border-[var(--line)]">
      <div class="flex items-center space-x-4">
        <span class="flex items-center gap-1.5">
          <span class="w-3 h-0.5 bg-[var(--blue)] inline-block"></span>
          Historical SPEI
        </span>
        <span class="flex items-center gap-1.5">
          <span class="w-3 h-0.5 bg-amber-500 border-b border-dashed border-amber-500 inline-block"></span>
          q50 Median
        </span>
        <span class="flex items-center gap-1.5">
          <span class="w-2.5 h-2.5 bg-[var(--blue)]/30 border border-[var(--blue)]/50 rounded-sm inline-block"></span>
          q10 - q90 Fan (80% CI)
        </span>
      </div>

      <div v-if="activeHorizonPoint" class="flex items-center space-x-2 text-[var(--ink)]">
        <span>Hasil +{{ selectedHorizon }} bulan:</span>
        <span class="text-[var(--red)] font-bold">q10: {{ activeHorizonPoint.q10 }}</span>
        <span>|</span>
        <span class="text-[var(--blue)] font-bold">q50: {{ activeHorizonPoint.q50 }}</span>
        <span>|</span>
        <span class="text-[var(--green)] font-bold">q90: {{ activeHorizonPoint.q90 }}</span>
      </div>
    </div>
  </div>
</template>
