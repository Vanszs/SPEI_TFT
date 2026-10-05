<script lang="ts">
import type { DroughtSeverity } from '../types';

export const getSpeiColor = (spei: number): string => {
  if (spei <= -2.0) return '#a33d2e';
  if (spei <= -1.5) return '#b45b2c';
  if (spei <= -1.0) return '#b77817';
  if (spei <= -0.5) return '#b58a2a';
  if (spei < 0.5) return '#2f7d68';
  if (spei < 1.5) return '#4c7a78';
  return '#56708a';
};

export const getSeverityBadge = (severity: DroughtSeverity) => {
  switch (severity) {
    case 'NORMAL':
      return { label: 'NORMAL (SPEI ≥ -0.5)', class: 'bg-[var(--soft-green)] text-[var(--green)] border-[var(--green)]' };
    case 'MODERATE':
      return { label: 'MODERATE (-1.5 < SPEI ≤ -0.5)', class: 'bg-[#f4ead5] text-[var(--amber)] border-[var(--amber)]' };
    case 'SEVERE':
      return { label: 'SEVERE (-2.0 < SPEI ≤ -1.5)', class: 'bg-[#f4e5d7] text-[#b45b2c] border-[#b45b2c]' };
    case 'EXTREME':
      return { label: 'EXTREME (SPEI ≤ -2.0)', class: 'bg-[#f3dfdc] text-[var(--red)] border-[var(--red)]' };
  }
};
</script>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { RegionPrediction } from '../types';

interface DroughtMapProps {
  regions: RegionPrediction[];
  selectedRegion: RegionPrediction;
  geoJsonData?: GeoJSON.FeatureCollection;
  height?: string;
  grid?: Array<{ id: string; city_id: string; lat: number; lon: number; spei: number; selected_rank?: number }>;
  gridVisible?: boolean;
  nodesVisible?: boolean;
}

const props = withDefaults(defineProps<DroughtMapProps>(), {
  height: '360px',
  grid: () => [],
  gridVisible: true,
  nodesVisible: true,
});

const emit = defineEmits<{
  (e: 'selectRegion', region: RegionPrediction): void;
  (e: 'toggleGrid'): void;
  (e: 'toggleNodes'): void;
}>();

const containerRef = ref<HTMLDivElement | null>(null);
let map: L.Map | null = null;
let geoJsonLayer: L.GeoJSON | null = null;
let markersLayer: L.LayerGroup | null = null;
let gridLayer: L.LayerGroup | null = null;
let vectorRenderer: L.Canvas | null = null;
let resizeObserver: ResizeObserver | null = null;

const regionMap = computed(() => {
  const m = new Map<string, RegionPrediction>();
  props.regions.forEach((r) => {
    m.set(r.id, r);
    m.set(r.regencyName.toLowerCase(), r);
  });
  return m;
});

const handleSelectRegion = (region: RegionPrediction) => {
  emit('selectRegion', region);
};

const handleToggleGrid = () => {
  emit('toggleGrid');
};

const handleToggleNodes = () => {
  emit('toggleNodes');
};

const updateGeoJson = () => {
  if (!map) return;

  if (geoJsonLayer) {
    map.removeLayer(geoJsonLayer);
    geoJsonLayer = null;
  }

  if (!props.geoJsonData) return;

  const layer = L.geoJSON(props.geoJsonData, {
    style: (feature) => {
      const id = feature?.properties?.bps_code || feature?.properties?.id || feature?.properties?.name;
      const region = id ? regionMap.value.get(String(id).toLowerCase()) || regionMap.value.get(String(feature?.properties?.name).toLowerCase()) : undefined;
      const spei = region ? region.speiForecast.q50 : 0;
      const isSelected = region?.id === props.selectedRegion.id;

      return {
        fillColor: region ? getSpeiColor(spei) : '#374151',
        weight: isSelected ? 2.5 : 1,
        opacity: 0.8,
        color: isSelected ? '#0b6f68' : '#8b9a95',
        fillOpacity: isSelected ? 0.75 : 0.45,
      };
    },
    onEachFeature: (feature, featureLayer) => {
      const p = feature.properties || {};
      const regencyName = p.name || p.regency || 'Regency';
      const region = regionMap.value.get(String(p.bps_code || p.id).toLowerCase()) || regionMap.value.get(String(regencyName).toLowerCase());

      const spei = region ? region.speiForecast.q50 : null;
      const tooltipContent = `
        <div style="font-family: monospace; font-size: 11px; padding: 2px;">
          <strong style="color: #263936;">${regencyName}</strong><br/>
          ${spei !== null ? `<span style="color: ${getSpeiColor(spei)};">SPEI q50: ${spei.toFixed(2)}</span>` : '<span style="color: #687873;">No Data</span>'}
        </div>
      `;

      featureLayer.bindTooltip(tooltipContent, {
        sticky: true,
        className: 'custom-leaflet-tooltip',
      });

      featureLayer.on({
        click: () => {
          if (region) handleSelectRegion(region);
        },
        mouseover: (e) => {
          const l = e.target;
          l.setStyle({ fillOpacity: 0.85, weight: 2 });
        },
        mouseout: (e) => {
          if (geoJsonLayer) {
            geoJsonLayer.resetStyle(e.target);
          }
        },
      });
    },
  }).addTo(map);

  geoJsonLayer = layer;
};

const updateGrid = () => {
  if (!gridLayer) return;
  gridLayer.clearLayers();
  if (!props.gridVisible || !props.grid) return;

  props.grid.forEach((cell) => {
    const halfDegree = 0.05;
    const dLat = halfDegree;
    const dLon = halfDegree;
    const bounds: L.LatLngBoundsExpression = [[cell.lat - dLat, cell.lon - dLon], [cell.lat + dLat, cell.lon + dLon]];
    const areaLabel = cell.selected_rank ? `Area ${cell.selected_rank}` : cell.id;
    const isAreaOne = cell.selected_rank === 1;
    L.rectangle(bounds, {
      color: isAreaOne ? '#0b6f68' : '#8b9a95',
      weight: isAreaOne ? 1.6 : 0.9,
      fillColor: getSpeiColor(cell.spei),
      fillOpacity: isAreaOne ? 0.28 : 0.18,
      renderer: vectorRenderer ?? undefined,
    })
      .bindTooltip(`${cell.city_id} · ${areaLabel}<br>SPEI: ${cell.spei.toFixed(2)}`, { sticky: true })
      .addTo(gridLayer!);
  });
};

const updateMarkers = () => {
  if (!markersLayer) return;
  markersLayer.clearLayers();
  if (!props.nodesVisible) return;

  props.regions.forEach((reg) => {
    const isSelected = reg.id === props.selectedRegion.id;
    const borderColor = isSelected ? '#0b6f68' : '#8b9a95';
    const size = isSelected ? 22 : 16;
    const iconHtml = `
      <div style="
        width: ${size}px;
        height: ${size}px;
        border-radius: 50%;
        background-color: #ffffff;
        border: 2px solid ${borderColor};
        box-shadow: ${isSelected ? '0 0 0 3px rgba(36,110,98,0.18)' : 'none'};
        transition: all 0.2s ease;
        cursor: pointer;
      "></div>
    `;

    const customIcon = L.divIcon({
      html: iconHtml,
      className: '',
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });

    const marker = L.marker(reg.coordinates, { icon: customIcon });

    marker.bindTooltip(
      `
      <div style="font-family: monospace; font-size: 11px; color: #f3f4f6;">
        <strong>${reg.regencyName}</strong> (${reg.province})<br/>
        <span style="color: #687873;">SPEI median: ${reg.speiForecast.q50.toFixed(2)}</span><br/>
        <span style="color: #687873;">Severity: ${reg.severity}</span>
      </div>
    `,
      { sticky: true, className: 'custom-leaflet-tooltip' }
    );

    marker.on('click', () => handleSelectRegion(reg));
    markersLayer!.addLayer(marker);
  });
};

const handleRecenter = () => {
  if (map && props.selectedRegion) {
    map.flyTo(props.selectedRegion.coordinates, 7, { duration: 1.2 });
  }
};

onMounted(() => {
  if (!containerRef.value) return;

  map = L.map(containerRef.value, {
    center: [-7.35, 112.25],
    zoom: 8,
    minZoom: 7,
    maxZoom: 12,
    zoomControl: false,
    attributionControl: true,
    preferCanvas: true,
    zoomAnimation: true,
    zoomAnimationThreshold: 4,
    wheelDebounceTime: 35,
    wheelPxPerZoomLevel: 90,
    maxBounds: [[-8.45, 110.55], [-6.45, 113.45]],
    maxBoundsViscosity: 0.85,
  });

  L.control.zoom({ position: 'topright' }).addTo(map);

  L.tileLayer(
    'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
    {
      maxZoom: 19,
      subdomains: 'abcd',
      detectRetina: true,
      attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; OpenStreetMap',
    }
  ).addTo(map);

  markersLayer = L.layerGroup().addTo(map);
  gridLayer = L.layerGroup().addTo(map);
  vectorRenderer = L.canvas({ padding: 1 });

  const eastJavaBounds = L.latLngBounds([-8.25, 110.85], [-6.65, 113.15]);
  map.fitBounds(eastJavaBounds, { padding: [24, 24] });

  updateGeoJson();
  updateGrid();
  updateMarkers();

  resizeObserver = new ResizeObserver(() => map?.invalidateSize());
  resizeObserver.observe(containerRef.value);
});

onUnmounted(() => {
  if (resizeObserver) {
    resizeObserver.disconnect();
    resizeObserver = null;
  }
  if (map) {
    map.remove();
    map = null;
    vectorRenderer = null;
  }
});

watch([() => props.geoJsonData, regionMap, () => props.selectedRegion], () => {
  updateGeoJson();
});

watch([() => props.grid, () => props.gridVisible], () => {
  updateGrid();
});

watch([() => props.regions, () => props.selectedRegion, () => props.nodesVisible], () => {
  updateMarkers();
});
</script>

<template>
  <div class="drought-map relative w-full rounded-lg overflow-hidden border border-slate-200 bg-white shadow-2xl">
    <!-- Map Container -->
    <div ref="containerRef" :style="{ height }" class="w-full z-0"></div>

    <!-- Map Header Overlay -->
    <div class="map-layer-label absolute top-3 left-3 z-[1000] bg-white/95 backdrop-blur-md px-3 py-1.5 rounded border border-slate-200 flex items-center gap-2 shadow-sm">
      <span class="w-2 h-2 rounded-full bg-[var(--green)]"></span>
      <span class="text-[11px] font-mono text-[var(--ink)] tracking-wider">
        GRID SPEI 0.1° · 5 WILAYAH
      </span>
    </div>

    <div class="map-layer-controls absolute top-3 left-3 z-[1000] flex gap-1">
      <button
        type="button"
        :aria-pressed="gridVisible"
        @click="handleToggleGrid"
        class="map-layer-toggle bg-white/95 border border-slate-200 px-2 py-1 text-[10px] font-mono text-slate-700 shadow-sm"
      >
        GRID {{ gridVisible ? 'AKTIF' : 'MATI' }}
      </button>
      <button
        type="button"
        :aria-pressed="nodesVisible"
        @click="handleToggleNodes"
        class="map-layer-toggle bg-white/95 border border-slate-200 px-2 py-1 text-[10px] font-mono text-slate-700 shadow-sm"
      >
        WILAYAH {{ nodesVisible ? 'AKTIF' : 'MATI' }}
      </button>
    </div>

    <!-- Recenter Button -->
    <button
      @click="handleRecenter"
      class="map-recenter absolute top-14 right-3 z-[1000] bg-white/95 hover:bg-slate-50 backdrop-blur-md text-slate-700 px-2.5 py-1 rounded border border-slate-200 text-xs font-mono transition-colors shadow-sm"
    >
      PUSATKAN {{ selectedRegion.regencyName.toUpperCase() }}
    </button>

    <!-- Anti-AI-Slop Minimal Legend Overlay -->
    <div class="absolute bottom-3 left-3 z-[1000] bg-white/95 backdrop-blur-md px-3 py-2 rounded border border-slate-200 text-[10px] font-mono space-y-1 shadow-sm">
      <span class="text-[var(--muted)] block font-semibold mb-1">GRID RISET · 5 sel per kabupaten</span>
      <div class="flex items-center gap-2 text-[var(--ink)]">
        <span class="w-3 h-3 rounded-sm bg-white border-2 border-[var(--green)]"></span>
        <span>pusat (Area 1)</span>
        <span class="w-3 h-3 rounded-sm bg-white border border-[var(--line)]"></span>
        <span>pendukung (Area 2–5)</span>
      </div>
    </div>
  </div>
</template>

<style>
.custom-leaflet-tooltip {
  background-color: #ffffff !important;
  border: 1px solid #b9c7c2 !important;
  border-radius: 4px !important;
  color: #263936 !important;
  box-shadow: 0 10px 15px -3px rgba(38, 57, 54, 0.16) !important;
  padding: 4px 8px !important;
}
.leaflet-tooltip-top:before,
.leaflet-tooltip-bottom:before,
.leaflet-tooltip-left:before,
.leaflet-tooltip-right:before {
  border-top-color: #b9c7c2 !important;
}
</style>
