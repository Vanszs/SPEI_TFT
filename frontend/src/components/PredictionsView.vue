<script setup lang="ts">
import { computed, ref } from 'vue';
import { ArrowUpRight, ChevronLeft } from 'lucide-vue-next';
import PredictionCard from './PredictionCard.vue';
import type { DroughtSeverity, Freshness, ModelMetrics, RegionPrediction } from '../types';

const props = defineProps<{
  regions: RegionPrediction[];
  status: string;
  model: ModelMetrics | null;
  freshness: Freshness;
  forecastStatus: 'active' | 'archived';
  asOf: string;
  dataAgeDays: number | null;
  isLoading: boolean;
}>();

const emit = defineEmits<{ (e: 'openForecast30', city: string): void }>();

const openRegion = ref<RegionPrediction | null>(null);

// Severity first, then the driest median. The reader needs to know where to act first.
const rank: Record<DroughtSeverity, number> = { EXTREME: 0, SEVERE: 1, MODERATE: 2, NORMAL: 3 };
const ordered = computed(() =>
  [...props.regions].sort(
    (a, b) => rank[a.severity] - rank[b.severity] || a.speiForecast.q50 - b.speiForecast.q50,
  ),
);
const lead = computed(() => ordered.value[0] ?? null);
const rest = computed(() => ordered.value.slice(1));
const atRisk = computed(() => props.regions.filter((r) => r.severity !== 'NORMAL').length);
const worst = computed(() => Math.min(...props.regions.map((r) => r.speiForecast.q50)));

const staleNotice = computed(() => {
  if (props.forecastStatus === 'archived') {
    return `Prakiraan 30 hari dari data ini sudah lewat. Data berhenti pada ${props.asOf}. Halaman ini adalah arsip, bukan kondisi terkini.`;
  }
  if (props.freshness === 'stale') {
    return `Data berhenti pada ${props.asOf} (${props.dataAgeDays ?? '—'} hari lalu). Angka di halaman ini bukan kondisi terkini.`;
  }
  return '';
});
</script>

<template>
  <section v-if="openRegion" class="detail-view" aria-label="Rincian prediksi wilayah">
    <button class="back-link" type="button" @click="openRegion = null">
      <ChevronLeft :size="15" /> Kembali ke semua wilayah
    </button>
    <div class="detail-head">
      <div>
        <h1>{{ openRegion.regencyName }}</h1>
        <p>{{ openRegion.province }} · SPEI observasi terakhir {{ openRegion.speiCurrent.toFixed(2) }}</p>
      </div>
    </div>
    <div class="detail-cta">
      <h2>Rincian harian ada di prakiraan 30 hari</h2>
      <p>
        Halaman ini menampilkan prakiraan satu langkah setelah data terakhir dari model yang sama.
        Rangkaian 30 hari beserta rentang P10–P90 ada di tab 30 Hari.
      </p>
      <button class="cta" type="button" @click="emit('openForecast30', openRegion.id)">
        Buka prediksi 30 hari {{ openRegion.regencyName.replace(/^Kab\.\s*/i, '') }} <ArrowUpRight :size="15" />
      </button>
    </div>
  </section>

  <section v-else class="card-view" aria-label="Prediksi per wilayah">
    <header class="view-head">
      <span class="eyebrow">Prediksi per wilayah</span>
      <h1>Lima kabupaten sentra padi Jawa Timur.</h1>
      <p>
        Prakiraan satu langkah setelah data terakhir (P50) dari Temporal Fusion Transformer.
        Rentang P10–P90 adalah ketidakpastian model, bukan peringatan resmi.
      </p>
      <div class="view-head__stats">
        <span><strong>{{ regions.length }}</strong> wilayah</span>
        <span><strong>{{ atRisk }}</strong> di atas normal</span>
        <span>SPEI terendah <strong>{{ Number.isFinite(worst) ? worst.toFixed(2) : '—' }}</strong></span>
      </div>
    </header>

    <div v-if="staleNotice" class="notice notice--error" role="alert">{{ staleNotice }}</div>

    <div class="horizon-bar">
      <span class="horizon-bar__label">Evaluasi</span>
      <span class="eval-tag">satu langkah setelah cutoff</span>
      <span class="horizon-bar__note">{{ model?.testPeriod ? `Periode uji ${model.testPeriod}` : status }}</span>
    </div>

    <p v-if="isLoading" class="notice" role="status">Memuat data penelitian…</p>
    <p v-else-if="!regions.length" class="notice" role="status">{{ status }}</p>

    <div v-else class="card-grid">
      <PredictionCard
        v-if="lead"
        :region="lead"
        featured
        @select="openRegion = $event"
      />
      <PredictionCard
        v-for="region in rest"
        :key="region.id"
        :region="region"
        @select="openRegion = $event"
      />
    </div>
  </section>
</template>
