<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { Activity, BookOpen, Download, Droplets, FileText, Gauge, Menu, Search, X } from 'lucide-vue-next';
import Forecast30View from './components/Forecast30View.vue';
import PredictionsView from './components/PredictionsView.vue';
import ExportModal from './components/ExportModal.vue';
import { DEFAULT_METRICS, fetchStudyData } from './api';
import type { RegionPrediction } from './types';
import { MOCK_REGIONS } from './data/mockData';

type ActiveView = 'forecast30' | 'predict' | 'method';

const views = [
  { id: 'forecast30' as const, label: '30 Hari', icon: Activity },
  { id: 'predict' as const, label: 'Wilayah', icon: Gauge },
  { id: 'method' as const, label: 'Metode', icon: BookOpen },
];

const activeView = ref<ActiveView>('forecast30');
const regions = ref<RegionPrediction[]>(MOCK_REGIONS);
const dataStatus = ref('DATA DUMMY · menunggu data penelitian');
const dataError = ref<string | null>(null);
const searchQuery = ref('');
const isExportOpen = ref(false);
const mobileNavOpen = ref(false);
const selectedRegionState = ref<RegionPrediction | null>(null);

let abortController: AbortController | null = null;

onMounted(() => {
  abortController = new AbortController();
  fetchStudyData(abortController.signal)
    .then((study) => {
      regions.value = study.regions;
      selectedRegionState.value = study.regions[0] ?? null;
      dataStatus.value = `${study.status} · observasi ${study.observationPeriod[0]}–${study.observationPeriod[1]}`;
    })
    .catch((error: unknown) => {
      if ((error as Error).name !== 'AbortError') {
        dataError.value = error instanceof Error ? error.message : 'Data penelitian gagal dimuat.';
        dataStatus.value = 'Data belum tersedia';
      }
    });
});

onUnmounted(() => abortController?.abort());

const filteredRegions = computed(() => {
  const query = searchQuery.value.trim().toLowerCase();
  if (!query) return [];
  return regions.value.filter((region) =>
    `${region.regencyName} ${region.province}`.toLowerCase().includes(query),
  );
});

const selectedRegion = computed(() => selectedRegionState.value ?? regions.value[0]);

const goToRegion = (region: RegionPrediction) => {
  selectedRegionState.value = region;
  activeView.value = 'forecast30';
  searchQuery.value = '';
};
</script>

<template>
  <div class="app">
    <a class="skip-link" href="#main">Lewati ke konten utama</a>

    <aside class="rail" aria-label="Navigasi utama">
      <button class="brand" type="button" @click="activeView = 'forecast30'" aria-label="NusaPantau, beranda">
        <Droplets :size="20" :stroke-width="1.8" />
        <span>NP</span>
      </button>
      <nav class="rail__nav">
        <button
          v-for="{ id, label, icon: Icon } in views"
          :key="id"
          type="button"
          @click="activeView = id"
          :class="{ 'is-on': activeView === id }"
          :aria-current="activeView === id ? 'page' : undefined"
        >
          <component :is="Icon" :size="18" :stroke-width="1.7" />
          <span>{{ label }}</span>
        </button>
      </nav>
    </aside>

    <header class="topbar">
      <div class="topbar__id">
        <button class="topbar__menu" type="button" @click="mobileNavOpen = !mobileNavOpen" aria-label="Buka navigasi" :aria-expanded="mobileNavOpen">
          <X v-if="mobileNavOpen" :size="20" />
          <Menu v-else :size="20" />
        </button>
        <button class="topbar__title" type="button" @click="activeView = 'forecast30'">
          <strong>NusaPantau Kekeringan</strong>
          <span>TFT · Pseudo-SPEI-3 Jawa Timur</span>
        </button>
      </div>

      <div class="topbar__actions">
        <div class="search">
          <Search :size="15" aria-hidden="true" />
          <input v-model="searchQuery" placeholder="Cari kabupaten" aria-label="Cari kabupaten" />
          <button v-if="searchQuery" type="button" @click="searchQuery = ''" aria-label="Hapus pencarian">
            <X :size="14" />
          </button>
          <ul v-if="filteredRegions.length" class="search__list" role="listbox">
            <li v-for="region in filteredRegions" :key="region.id">
              <button type="button" role="option" @click="goToRegion(region)">
                <strong>{{ region.regencyName }}</strong>
                <span>{{ region.province }}</span>
              </button>
            </li>
          </ul>
        </div>
        <button class="icon-btn" type="button" @click="isExportOpen = true" aria-label="Unduh laporan">
          <Download :size="17" />
        </button>
      </div>

      <nav v-if="mobileNavOpen" class="mobile-nav" aria-label="Navigasi mobile">
        <button
          v-for="{ id, label, icon: Icon } in views"
          :key="id"
          type="button"
          @click="activeView = id; mobileNavOpen = false"
          :class="{ 'is-on': activeView === id }"
        >
          <component :is="Icon" :size="18" /> {{ label }}
        </button>
      </nav>
    </header>

    <main id="main" class="main">
      <Forecast30View v-if="activeView === 'forecast30' && !dataError" />

      <div v-if="dataError" class="notice notice--error" role="alert">{{ dataError }}</div>
      <div v-else-if="!regions.length" class="notice" role="status">{{ dataStatus }}</div>

      <PredictionsView v-if="activeView === 'predict' && !dataError" :regions="regions" :status="dataStatus" @open-forecast30="activeView = 'forecast30'" />

      <section v-if="activeView === 'method'" class="method" aria-label="Metodologi">
        <header class="view-head">
          <span class="eyebrow">Metodologi</span>
          <h1>Dari data cuaca ke indeks kekeringan.</h1>
          <p>Ringkasan alur penelitian, supaya angka pada kartu prediksi bisa dibaca dengan tepat.</p>
        </header>
        <ol class="method__steps">
          <li>
            <Droplets :size="20" />
            <div>
              <h2>Neraca air harian</h2>
              <p>Curah hujan dikurangi evapotranspirasi referensi (P − ET0) dari Open-Meteo Archive.</p>
            </div>
          </li>
          <li>
            <FileText :size="20" />
            <div>
              <h2>Pseudo-SPEI-3</h2>
              <p>Defisit diakumulasi 90 hari, lalu dipetakan ke skor baku lewat distribusi log-logistic per bulan.</p>
            </div>
          </li>
          <li>
            <Activity :size="20" />
            <div>
              <h2>Temporal Fusion Transformer</h2>
              <p>Encoder 90 hari memproyeksikan kuantil P10, P50, dan P90 hingga 30 hari ke depan.</p>
            </div>
          </li>
        </ol>
        <dl class="method__metrics">
          <div><dt>Skill score</dt><dd>{{ (DEFAULT_METRICS.skillScore * 100).toFixed(1) }}%</dd></div>
          <div><dt>RMSE</dt><dd>{{ DEFAULT_METRICS.rmse.toFixed(3) }}</dd></div>
          <div><dt>MAE</dt><dd>{{ DEFAULT_METRICS.mae.toFixed(3) }}</dd></div>
        </dl>
      </section>

      <footer class="footer">
        <span>{{ regions.length }} kabupaten studi</span>
        <span>Riset TFT-SPEI · 2026</span>
      </footer>
    </main>

    <ExportModal
      :is-open="isExportOpen"
      @close="isExportOpen = false"
      :regions="regions"
      :selected-region="selectedRegion"
    />
  </div>
</template>
