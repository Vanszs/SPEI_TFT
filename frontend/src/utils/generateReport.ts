import { jsPDF } from 'jspdf';
import type { ModelMetrics, RegionPrediction } from '../types';

export function exportToCSV(regions: RegionPrediction[]) {
  const headers = ['BPS ID', 'Regency', 'Province', 'Latitude', 'Longitude', 'Current SPEI', 'Evaluation p10', 'Evaluation p50', 'Evaluation p90', 'Severity'];
  const rows = regions.map((r) => [
    r.id,
    `"${r.regencyName}"`,
    `"${r.province}"`,
    r.coordinates[0],
    r.coordinates[1],
    r.speiCurrent.toFixed(2),
    r.speiForecast.q10.toFixed(2),
    r.speiForecast.q50.toFixed(2),
    r.speiForecast.q90.toFixed(2),
    r.severity,
  ]);

  const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((e) => e.join(','))].join('\n');
  const link = document.createElement('a');
  link.setAttribute('href', encodeURI(csvContent));
  link.setAttribute('download', `SPEI_Forecast_Export_${new Date().toISOString().slice(0, 10)}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export function exportToGeoJSON(regions: RegionPrediction[]) {
  const geojson = {
    type: 'FeatureCollection',
    features: regions.map((r) => ({
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [r.coordinates[1], r.coordinates[0]], // GeoJSON uses [lng, lat]
      },
      properties: {
        id: r.id,
        regencyName: r.regencyName,
        province: r.province,
        speiCurrent: r.speiCurrent,
        evaluation: r.speiForecast,
        severity: r.severity,
      },
    })),
  };

  const blob = new Blob([JSON.stringify(geojson, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `SPEI_Forecast_GeoJSON_${new Date().toISOString().slice(0, 10)}.geojson`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

const pct = (value: number | null) => (value === null ? '—' : `${(value * 100).toFixed(1)}%`);
const num = (value: number | null, digits = 3) => (value === null ? '—' : value.toFixed(digits));

export async function generatePDFReport(region: RegionPrediction, metrics?: ModelMetrics | null) {
  const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });

  doc.setFillColor(14, 20, 32);
  doc.rect(0, 0, 210, 30, 'F');
  doc.setTextColor(255, 255, 255);
  doc.setFontSize(16);
  doc.setFont('helvetica', 'bold');
  doc.text('INDONESIA HYDRO-METEOROLOGICAL SPEI REPORT', 14, 15);
  doc.setFontSize(9);
  doc.setFont('helvetica', 'normal');
  doc.setTextColor(148, 163, 184);
  doc.text(`Generated: ${new Date().toLocaleString()} • Public Handover Release`, 14, 23);

  doc.setFillColor(241, 245, 249);
  doc.rect(14, 38, 182, 40, 'F');
  doc.setDrawColor(203, 213, 225);
  doc.rect(14, 38, 182, 40, 'S');

  doc.setFontSize(14);
  doc.setFont('helvetica', 'bold');
  doc.setTextColor(15, 23, 42);
  doc.text(`${region.regencyName}, ${region.province}`, 20, 48);

  doc.setFontSize(10);
  doc.setFont('helvetica', 'normal');
  doc.setTextColor(71, 85, 105);
  doc.text(`BPS Region ID: ${region.id}   |   Coordinates: ${region.coordinates[0]}°, ${region.coordinates[1]}°`, 20, 56);
  doc.text(`Current SPEI Index: ${region.speiCurrent.toFixed(2)}   |   Status: ${region.severity}`, 20, 64);
  doc.text(
    `Evaluation t+1: p10=${region.speiForecast.q10.toFixed(2)} | p50=${region.speiForecast.q50.toFixed(2)} | p90=${region.speiForecast.q90.toFixed(2)}`,
    20,
    72,
  );

  let currentY = 88;

  if (metrics) {
    doc.setFontSize(11);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(15, 23, 42);
    doc.text('Model Verification & Quality Metrics', 14, currentY);
    currentY += 6;

    const tableData = [
      ['Checkpoint', metrics.checkpoint ?? '—'],
      ['Skill score (all horizons)', pct(metrics.skillScoreAllHorizons)],
      ['Skill score (t+1)', pct(metrics.skillScoreT1)],
      ['Interval coverage (t+1)', pct(metrics.picp)],
      ['RMSE / MAE (t+1)', `${num(metrics.rmse)} / ${num(metrics.mae)}`],
      ['Test period', metrics.testPeriod ?? '—'],
      ['Evaluation samples', metrics.n === null ? '—' : String(metrics.n)],
    ];

    doc.setFontSize(9);
    doc.setFont('helvetica', 'normal');
    tableData.forEach(([label, value]) => {
      doc.setFillColor(248, 250, 252);
      doc.rect(14, currentY, 90, 7, 'F');
      doc.rect(104, currentY, 92, 7, 'F');
      doc.setDrawColor(226, 232, 240);
      doc.rect(14, currentY, 90, 7, 'S');
      doc.rect(104, currentY, 92, 7, 'S');
      doc.setTextColor(100, 116, 139);
      doc.text(label, 18, currentY + 5);
      doc.setTextColor(15, 23, 42);
      doc.text(String(value), 108, currentY + 5);
      currentY += 7;
    });
  }

  doc.setFontSize(8);
  doc.setTextColor(148, 163, 184);
  doc.text('Temporal Fusion Transformer SPEI Forecasting System • Automated Public Handover PDF', 14, 285);

  doc.save(`SPEI_Report_${region.id}_${new Date().toISOString().slice(0, 10)}.pdf`);
}
