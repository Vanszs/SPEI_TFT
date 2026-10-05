<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import {
  Activity,
  BookOpen,
  ChevronDown,
  ChevronUp,
  Download,
  Droplets,
  FileText,
  Map,
  Menu,
  Search,
  ShieldAlert,
  X,
} from 'lucide-vue-next';
import DroughtMap from './components/DroughtMap.vue';
import ExportModal from './components/ExportModal.vue';
import TFTFanChart from './components/TFTFanChart.vue';
import { DEFAULT_METRICS, fetchStudyData } from './api';
import type { DroughtSeverity, RegionPrediction } from './types';
import { MOCK_REGIONS } from './data/mockData';

type ActiveView = 'map' | 'forecast' | 'risk' | 'method';

const severityMeta: Record<DroughtSeverity, { label: string; className: string; action: string }> = {
  NORMAL: {
    label: 'Normal',
    className: 'severity-normal',
    action: 'Pantau rutin dan pertahankan cadangan air untuk periode berikutnya.',
  },
  MODERATE: {
    label: 'Waspada',
    className: 'severity-moderate',
    action: 'Atur irigasi lebih hemat dan mulai menyiapkan sumber air alternatif.',
  },
  SEVERE: {
    label: 'Siaga',
    className: 'severity-severe',
    action: 'Prioritaskan distribusi air, tanaman tahan kering, dan kesiapan pompa irigasi.',
  },
  EXTREME: {
    label: 'Awas',
    className: 'severity-extreme',
    action: 'Aktifkan langkah tanggap kekeringan bersama BPBD, dinas pertanian, dan desa.',
  },
};

const views = [
  { id: 'map' as const, label: 'Peta', icon: Map },
  { id: 'forecast' as const, label: 'Prediksi', icon: Activity },
  { id: 'risk' as const, label: 'Risiko', icon: ShieldAlert },
  { id: 'method' as const, label: 'Metode', icon: BookOpen },
];

const EMPTY_REGION: RegionPrediction = {
  id: 'loading',
  regencyName: 'Memuat wilayah...',
  province: 'Jawa Timur',
  speiCurrent: 0,
  speiForecast: { q10: 0, q50: 0, q90: 0 },
  severity: 'NORMAL',
  coordinates: [-7.25, 112.75],
  historicalSpei: [],
};

const activeView = ref<ActiveView>('map');
const selectedHorizon = ref(3);
const selectedAreaId = ref<string | null>(null);
const regions = ref<RegionPrediction[]>(MOCK_REGIONS);
const studyGrid = ref<Array<{ id: string; city_id: string; lat: number; lon: number; spei: number; selected_rank?: number }>>(
  MOCK_REGIONS.flatMap((region) => {
    const offsets = [
      { dLat: 0.0, dLon: 0.0 },
      { dLat: -0.08, dLon: -0.08 },
      { dLat: 0.0, dLon: -0.12 },
      { dLat: -0.08, dLon: 0.08 },
      { dLat: 0.08, dLon: -0.08 },
    ];
    return offsets.map((offset, index) => ({
      id: `${region.id}__n${String(index).padStart(2, '0')}__fallback`,
      city_id: region.id,
      lat: region.coordinates[0] + offset.dLat,
      lon: region.coordinates[1] + offset.dLon,
      spei: region.speiForecast.q50,
      selected_rank: index + 1,
    }));
  }),
);
const gridVisible = ref(true);
const nodesVisible = ref(true);
const isAnalysisExpanded = ref(false);
const selectedRegionState = ref<RegionPrediction | null>(null);
const dataStatus = ref('DATA DUMMY · menunggu data penelitian');
const dataError = ref<string | null>(null);
const searchQuery = ref('');
const isExportOpen = ref(false);
const mobileNavOpen = ref(false);

let abortController: AbortController | null = null;

onMounted(() => {
  abortController = new AbortController();
  fetchStudyData(abortController.signal)
    .then((study) => {
      regions.value = study.regions;
      studyGrid.value = study.grid;
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

onUnmounted(() => {
  abortController?.abort();
});

const filteredRegions = computed(() => {
  const query = searchQuery.value.trim().toLowerCase();
  if (!query) return [];
  return regions.value.filter((region) =>
    `${region.regencyName} ${region.province}`.toLowerCase().includes(query),
  );
});

const selectedRegion = computed(() => selectedRegionState.value ?? regions.value[0] ?? EMPTY_REGION);
const selectedSeverity = computed(() => severityMeta[selectedRegion.value.severity]);
const watchedCount = computed(() => regions.value.length);
const atRiskCount = computed(() => regions.value.filter((region) => region.severity !== 'NORMAL').length);

const selectRegion = (region: RegionPrediction) => {
  selectedRegionState.value = region;
  searchQuery.value = '';
  activeView.value = 'map';
};

const selectForecastRegion = (region: RegionPrediction) => {
  selectedRegionState.value = region;
  selectedHorizon.value = 3;
};

const selectedGrid = computed(() => {
  const keys = new Set([
    selectedRegion.value.id.toLowerCase(),
    selectedRegion.value.regencyName.toLowerCase().replace(/^kab\.\s*/i, ''),
  ]);
  return studyGrid.value.filter((cell) =>
    keys.has(cell.city_id.toLowerCase().replace(/^kab\.\s*/i, ''))
  );
});

const activeArea = computed(() => {
  return (
    selectedGrid.value.find((cell) => String(cell.selected_rank ?? '') === selectedAreaId.value) ??
    selectedGrid.value[0]
  );
});
</script>

<template>
  <div class="drought-app">
    <a class="skip-link" href="#workspace">Langsung ke peta dan analisis</a>

    <aside class="side-rail" aria-label="Navigasi utama">
      <button class="brand-mark" @click="activeView = 'map'" aria-label="NusaPantau, halaman utama">
        <Droplets :size="21" :stroke-width="1.8" />
        <span>NP</span>
      </button>
      <nav class="rail-nav">
        <button
          v-for="{ id, label, icon: Icon } in views"
          :key="id"
          @click="activeView = id"
          :class="{ 'is-active': activeView === id }"
          :aria-current="activeView === id ? 'page' : undefined"
          :title="label"
        >
          <component :is="Icon" :size="18" :stroke-width="1.7" />
          <span>{{ label }}</span>
        </button>
      </nav>
    </aside>

    <header class="app-bar">
      <div class="app-identity">
        <button
          class="mobile-menu"
          @click="mobileNavOpen = !mobileNavOpen"
          aria-label="Buka navigasi"
          :aria-expanded="mobileNavOpen"
        >
          <X v-if="mobileNavOpen" :size="20" />
          <Menu v-else :size="20" />
        </button>
        <button class="identity-copy" @click="activeView = 'map'">
          <strong>NusaPantau Kekeringan</strong>
          <span>Proyeksi SPEI Jawa Timur</span>
        </button>
        <span class="data-badge">DATA PENELITIAN</span>
      </div>

      <div class="app-actions">
        <div class="search-control">
          <Search :size="16" aria-hidden="true" />
          <input
            v-model="searchQuery"
            placeholder="Cari kabupaten"
            aria-label="Cari kabupaten"
          />
          <button v-if="searchQuery" @click="searchQuery = ''" aria-label="Hapus pencarian">
            <X :size="15" />
          </button>
          <div v-if="filteredRegions.length > 0" class="search-results" role="listbox">
            <button
              v-for="region in filteredRegions"
              :key="region.id"
              @click="selectRegion(region)"
              role="option"
            >
              <strong>{{ region.regencyName }}</strong>
              <span>{{ region.province }}</span>
            </button>
          </div>
        </div>
        <button
          class="icon-button"
          @click="isExportOpen = true"
          title="Unduh laporan"
          aria-label="Unduh laporan"
        >
          <Download :size="18" />
        </button>
      </div>

      <nav v-if="mobileNavOpen" class="mobile-nav" aria-label="Navigasi utama mobile">
        <button
          v-for="{ id, label, icon: Icon } in views"
          :key="id"
          @click="activeView = id; mobileNavOpen = false"
          :class="{ 'is-active': activeView === id }"
        >
          <component :is="Icon" :size="18" /> {{ label }}
        </button>
      </nav>
    </header>

    <main id="workspace" class="workspace">
      <div v-if="dataError" class="data-error" role="alert">{{ dataError }}</div>
      <div v-if="!dataError && regions.length === 0" class="data-loading" role="status">{{ dataStatus }}</div>
      <section v-if="activeView === 'map'" class="map-workspace" aria-label="Peta dan analisis kekeringan">
        <div class="map-stage">
          <DroughtMap
            :regions="regions"
            :grid="studyGrid"
            :grid-visible="gridVisible"
            :nodes-visible="nodesVisible"
            @toggle-grid="gridVisible = !gridVisible"
            @toggle-nodes="nodesVisible = !nodesVisible"
            :selected-region="selectedRegion"
            @select-region="selectRegion"
            height="100%"
          />
          <div class="map-intro">
            <span>PROYEK SKRIPSI</span>
            <h1>Perkiraan risiko kekeringan untuk lima wilayah studi.</h1>
            <p>Pilih titik pada peta untuk membaca proyeksi SPEI dan rentang ketidakpastiannya.</p>
          </div>
          <div class="map-sample-note">{{ dataStatus }}. Bukan peringatan operasional.</div>
        </div>

        <section :class="['analysis-drawer', { 'is-expanded': isAnalysisExpanded }]" aria-label="Analisis wilayah terpilih">
          <div class="drawer-heading">
            <div>
              <p>ANALISIS WILAYAH</p>
              <h2>{{ selectedRegion.regencyName }}</h2>
              <span>{{ selectedRegion.province }} · {{ selectedRegion.coordinates[0].toFixed(3) }}, {{ selectedRegion.coordinates[1].toFixed(3) }}</span>
            </div>
            <div class="flex items-center gap-2">
              <div class="horizon-control" aria-label="Pilih horizon prediksi">
                <button
                  v-for="horizon in [1, 3, 6, 12]"
                  :key="horizon"
                  @click="selectedHorizon = horizon"
                  :class="{ 'is-selected': selectedHorizon === horizon }"
                >
                  +{{ horizon }} bln
                </button>
              </div>
              <button
                type="button"
                :aria-expanded="isAnalysisExpanded"
                :aria-label="isAnalysisExpanded ? 'Ringkas analisis' : 'Perluas analisis'"
                @click="isAnalysisExpanded = !isAnalysisExpanded"
                class="drawer-toggle"
                :title="isAnalysisExpanded ? 'Ringkas analisis' : 'Perluas analisis'"
              >
                <ChevronDown v-if="isAnalysisExpanded" :size="16" />
                <ChevronUp v-else :size="16" />
              </button>
            </div>
          </div>

          <div class="analysis-grid">
            <div class="analysis-panel chart-panel">
              <TFTFanChart
                :region="selectedRegion"
                :selected-horizon="selectedHorizon"
                @horizon-change="(h: number) => selectedHorizon = h"
              />
            </div>
            <section class="analysis-panel severity-panel">
              <div :class="['severity-status', selectedSeverity.className]">
                <span>Status +{{ selectedHorizon }} bulan</span>
                <strong>{{ selectedSeverity.label }}</strong>
                <b>SPEI median {{ selectedRegion.speiForecast.q50.toFixed(2) }}</b>
              </div>
              <p>{{ selectedSeverity.action }}</p>
              <button @click="activeView = 'risk'">Buka rekomendasi</button>
            </section>
            <section class="analysis-panel model-panel">
              <p>VALIDASI MODEL</p>
              <strong>{{ (DEFAULT_METRICS.skillScore * 100).toFixed(1) }}%</strong>
              <span>skill score multi-seed</span>
              <dl>
                <div><dt>RMSE</dt><dd>{{ DEFAULT_METRICS.rmse.toFixed(3) }}</dd></div>
                <div><dt>MAE</dt><dd>{{ DEFAULT_METRICS.mae.toFixed(3) }}</dd></div>
              </dl>
            </section>
          </div>
        </section>
      </section>

      <section v-if="activeView === 'forecast'" class="standalone-view forecast-view">
        <header>
          <span>PREDIKSI PROBABILISTIK</span>
          <h1>Prediksi lima wilayah studi</h1>
          <p>Pilih kabupaten untuk membaca lintasan SPEI, rentang kemungkinan, dan grid sumber model.</p>
        </header>
        <div class="forecast-layout">
          <aside class="forecast-sidebar" aria-label="Daftar wilayah dan grid penelitian">
            <div class="forecast-sidebar__heading">
              <strong>WILAYAH STUDI</strong>
              <span>{{ regions.length }} kabupaten</span>
            </div>
            <div class="forecast-region-list">
              <button
                v-for="region in regions"
                :key="region.id"
                type="button"
                :class="['forecast-region', { 'is-selected': region.id === selectedRegion.id }]"
                @click="selectForecastRegion(region)"
                :aria-pressed="region.id === selectedRegion.id"
              >
                <span class="forecast-region__top">
                  <strong>{{ region.regencyName.replace(/^Kab\.\s*/i, '') }}</strong>
                  <b :class="severityMeta[region.severity].className">{{ severityMeta[region.severity].label }}</b>
                </span>
                <span class="forecast-region__meta">
                  SPEI {{ region.speiForecast.q50.toFixed(2) }} · {{ studyGrid.filter((cell) => cell.city_id.toLowerCase().replace(/^kab\.\s*/i, '') === region.id.toLowerCase().replace(/^kab\.\s*/i, '')).length || '—' }} grid
                </span>
              </button>
            </div>
            <div class="forecast-grid-detail">
              <div class="forecast-sidebar__heading">
                <strong>GRID {{ selectedRegion.regencyName.replace(/^Kab\.\s*/i, '').toUpperCase() }}</strong>
                <span>{{ selectedGrid.length }} cell</span>
              </div>
              <div class="forecast-grid-list">
                <button
                  v-for="cell in selectedGrid"
                  :key="cell.id"
                  type="button"
                  :class="['forecast-grid-row', { 'is-selected': String(cell.selected_rank ?? '') === String(activeArea?.selected_rank ?? '') }]"
                  @click="selectedAreaId = String(cell.selected_rank ?? cell.id)"
                  :aria-pressed="String(cell.selected_rank ?? '') === String(activeArea?.selected_rank ?? '')"
                >
                  <span>
                    <b>{{ cell.selected_rank ? `Area ${cell.selected_rank}` : cell.id }}</b>
                    <small>{{ cell.lat.toFixed(3) }}, {{ cell.lon.toFixed(3) }}</small>
                  </span>
                  <strong>{{ cell.spei.toFixed(2) }}</strong>
                </button>
                <p v-if="selectedGrid.length === 0" class="forecast-empty">
                  Grid source belum tersedia untuk wilayah ini.
                </p>
              </div>
            </div>
          </aside>
          <div class="standalone-chart">
            <div class="forecast-area-context">
              <strong>{{ activeArea ? `Area ${activeArea.selected_rank ?? 'aktif'}` : 'Area belum dipilih' }}</strong>
              <span>Forecast model tersedia pada level kabupaten; nilai area menunjukkan cell sumber {{ activeArea ? `· SPEI ${activeArea.spei.toFixed(2)}` : '' }}.</span>
            </div>
            <TFTFanChart
              :region="selectedRegion"
              :selected-horizon="selectedHorizon"
              @horizon-change="(h: number) => selectedHorizon = h"
            />
          </div>
        </div>
      </section>

      <section v-if="activeView === 'risk'" class="standalone-view risk-view">
        <header>
          <span>RISIKO WILAYAH STUDI</span>
          <h1>Prioritas respons kekeringan</h1>
          <p>Urutkan tindakan dari hasil proyeksi, bukan status peringatan resmi.</p>
        </header>
        <div class="risk-list">
          <button
            v-for="region in regions"
            :key="region.id"
            @click="selectRegion(region)"
            class="risk-row"
          >
            <div>
              <strong>{{ region.regencyName }}</strong>
              <span>{{ region.province }}</span>
            </div>
            <span :class="['risk-label', severityMeta[region.severity].className]">
              {{ severityMeta[region.severity].label }}
            </span>
            <b>{{ region.speiForecast.q50.toFixed(2) }}</b>
            <span class="risk-action">{{ severityMeta[region.severity].action }}</span>
          </button>
        </div>
      </section>

      <section v-if="activeView === 'method'" class="standalone-view method-view">
        <header>
          <span>METODOLOGI</span>
          <h1>Dari cuaca ke indeks kekeringan</h1>
          <p>Ringkasan alur penelitian untuk membaca hasil visualisasi secara tepat.</p>
        </header>
        <div class="method-grid">
          <article>
            <Droplets :size="22" />
            <h2>Data cuaca</h2>
            <p>Curah hujan dan evapotranspirasi dari Open-Meteo membentuk neraca air.</p>
          </article>
          <article>
            <Activity :size="22" />
            <h2>Indeks SPEI</h2>
            <p>Neraca air dihitung dalam skala waktu untuk mengukur kondisi kering atau basah.</p>
          </article>
          <article>
            <FileText :size="22" />
            <h2>Model TFT</h2>
            <p>Temporal Fusion Transformer memproyeksikan q10, q50, dan q90 hingga 12 bulan.</p>
          </article>
        </div>
      </section>

      <footer class="workspace-footer">
        <span>{{ watchedCount }} kabupaten studi</span>
        <span>{{ atRiskCount }} wilayah berada di atas status normal pada contoh ini</span>
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
