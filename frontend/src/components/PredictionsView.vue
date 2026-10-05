<script setup lang="ts">
import { computed, ref } from 'vue';
import { ArrowUpRight, ChevronLeft } from 'lucide-vue-next';
import PredictionCard from './PredictionCard.vue';
import type { DroughtSeverity, RegionPrediction } from '../types';

const props = defineProps<{
  regions: RegionPrediction[];
  status: string;
}>();

const emit = defineEmits<{ (e: 'openForecast30'): void }>();

const HORIZONS = [1, 3, 6, 12] as const;
const horizon = ref<number>(3);
const openRegion = ref<RegionPrediction | null>(null);

// Severity first, then the driest median. The reader needs to know where to act first,
// so alphabetical order would be actively unhelpful here.
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
</script>

<template>
  <section v-if="openRegion" class="detail-view" aria-label="Rincian prediksi wilayah">
    <button class="back-link" type="button" @click="openRegion = null">
      <ChevronLeft :size="15" /> Kembali ke semua wilayah
    </button>
    <div class="detail-head">
      <div>
        <h1>{{ openRegion.regencyName }}</h1>
        <p>
          Proyeksi Pseudo-SPEI-3 · {{ openRegion.province }} ·
          SPEI terakhir {{ openRegion.speiCurrent.toFixed(2) }}
        </p>
      </div>
      <div class="horizon" role="group" aria-label="Pilih horizon prediksi">
        <button
          v-for="h in HORIZONS"
          :key="h"
          type="button"
          :class="{ 'is-on': horizon === h }"
          :aria-pressed="horizon === h"
          @click="horizon = h"
        >
          +{{ h }} bln
        </button>
      </div>
    </div>
    <div class="detail-cta">
      <h2>Rincian harian ada di prakiraan 30 hari</h2>
      <p>
        Grafik di halaman ini dulu menampilkan 12 bulan hasil interpolasi, bukan keluaran model.
        Nilai sebenarnya adalah 30 hari ke depan dengan rentang P10–P90.
      </p>
      <button class="cta" type="button" @click="emit('openForecast30')">
        Buka prediksi 30 hari {{ openRegion.regencyName.replace(/^Kab\.\s*/i, '') }} <ArrowUpRight :size="15" />
      </button>
    </div>
  </section>

  <section v-else class="card-view" aria-label="Prediksi per wilayah">
    <header class="view-head">
      <span class="eyebrow">Prediksi per wilayah</span>
      <h1>Lima kabupaten sentra padi Jawa Timur.</h1>
      <p>
        Pseudo-SPEI-3 dari Temporal Fusion Transformer. Rentang P10–P90 adalah ketidakpastian
        model pada horizon yang dipilih, bukan peringatan resmi.
      </p>
      <div class="view-head__stats">
        <span><strong>{{ regions.length }}</strong> wilayah</span>
        <span><strong>{{ atRisk }}</strong> di atas normal</span>
        <span>SPEI terendah <strong>{{ Number.isFinite(worst) ? worst.toFixed(2) : '—' }}</strong></span>
      </div>
    </header>

    <div class="horizon-bar">
      <span class="horizon-bar__label">Horizon</span>
      <div class="horizon" role="group" aria-label="Pilih horizon prediksi">
        <button
          v-for="h in HORIZONS"
          :key="h"
          type="button"
          :class="{ 'is-on': horizon === h }"
          :aria-pressed="horizon === h"
          @click="horizon = h"
        >
          +{{ h }} bln
        </button>
      </div>
      <span class="horizon-bar__note">{{ status }}</span>
    </div>

    <div class="card-grid">
      <PredictionCard
        v-if="lead"
        :region="lead"
        :horizon="horizon"
        featured
        @select="openRegion = $event"
      />
      <PredictionCard
        v-for="region in rest"
        :key="region.id"
        :region="region"
        :horizon="horizon"
        @select="openRegion = $event"
      />
    </div>
  </section>
</template>
