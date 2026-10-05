<script setup lang="ts">
import { ref } from 'vue';
import { Download, FileText, Globe, Table, X } from 'lucide-vue-next';
import type { RegionPrediction, ModelMetrics } from '../types';
import { exportToCSV, exportToGeoJSON, generatePDFReport } from '../utils/generateReport';

interface ExportModalProps {
  isOpen: boolean;
  regions: RegionPrediction[];
  selectedRegion: RegionPrediction;
  metrics?: ModelMetrics;
  chartElementId?: string;
}

const props = defineProps<ExportModalProps>();
const emit = defineEmits<{
  (e: 'close'): void;
}>();

const isExportingPDF = ref(false);

const handleClose = () => {
  emit('close');
};

const handleExportPDF = async () => {
  isExportingPDF.value = true;
  try {
    await generatePDFReport(props.selectedRegion, props.metrics, props.chartElementId);
  } finally {
    isExportingPDF.value = false;
  }
};

const actionClass = 'w-full flex items-center justify-between gap-3 p-3 bg-[#f3f6f2] hover:bg-[var(--soft-green)] border border-[var(--line)] rounded-lg group transition-colors text-left';
const titleClass = 'text-xs font-mono font-semibold text-[var(--ink)]';
const copyClass = 'text-[10px] text-[var(--muted)]';
const iconClass = 'w-5 h-5';
</script>

<template>
  <div v-if="isOpen" class="fixed inset-0 z-50 bg-[#263936]/45 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="bg-[var(--surface)] border border-[var(--line)] rounded-xl w-full max-w-md overflow-hidden shadow-2xl">
      <div class="flex items-center justify-between p-4 border-b border-[var(--line)]">
        <div class="flex items-center gap-2">
          <Download class="w-4 h-4 text-[var(--green)]" />
          <h3 class="text-sm font-mono font-semibold text-[var(--ink)]">EXPORT SPEI DATA &amp; REPORTS</h3>
        </div>
        <button @click="handleClose" aria-label="Tutup ekspor" class="text-[var(--muted)] hover:text-[var(--ink)]">
          <X class="w-4 h-4" />
        </button>
      </div>

      <div class="p-5 space-y-4">
        <p class="text-xs text-[var(--muted)] font-mono">
          Select format for public handover / research download:
        </p>

        <div class="space-y-2.5">
          <button @click="exportToCSV(regions); handleClose();" :class="actionClass">
            <div class="flex items-center gap-3">
              <Table :class="`${iconClass} text-[var(--green)]`" />
              <div>
                <div :class="titleClass">CSV Format (.csv)</div>
                <div :class="copyClass">Raw SPEI tabular dataset for all {{ regions.length }} regencies</div>
              </div>
            </div>
            <Download class="w-4 h-4 text-[var(--muted)] group-hover:text-[var(--green)]" />
          </button>

          <button @click="exportToGeoJSON(regions); handleClose();" :class="actionClass">
            <div class="flex items-center gap-3">
              <Globe :class="`${iconClass} text-[var(--blue)]`" />
              <div>
                <div :class="titleClass">GeoJSON Format (.geojson)</div>
                <div :class="copyClass">GIS feature collection with coordinates &amp; metadata</div>
              </div>
            </div>
            <Download class="w-4 h-4 text-[var(--muted)] group-hover:text-[var(--blue)]" />
          </button>

          <button @click="handleExportPDF" :disabled="isExportingPDF" :class="`${actionClass} disabled:opacity-50`">
            <div class="flex items-center gap-3">
              <FileText :class="`${iconClass} text-[var(--amber)]`" />
              <div>
                <div :class="titleClass">PDF Executive Report (.pdf)</div>
                <div :class="copyClass">Print-ready report for {{ selectedRegion.regencyName }} with embedded chart</div>
              </div>
            </div>
            <span v-if="isExportingPDF" class="text-[10px] font-mono text-[var(--amber)] animate-pulse">Generating...</span>
            <Download v-else class="w-4 h-4 text-[var(--muted)] group-hover:text-[var(--amber)]" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
