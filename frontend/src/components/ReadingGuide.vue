<script setup lang="ts">
defineProps<{ compact?: boolean }>();
</script>

<template>
  <details class="glossary" :class="{ 'glossary--compact': compact }">
    <summary>Cara membaca angka di halaman ini</summary>
    <dl>
      <div>
        <dt>SPEI</dt>
        <dd>Ukuran kering-basah dibanding tahun-tahun sebelumnya. <b>0 = normal</b>, negatif berarti lebih kering, positif lebih basah.</dd>
      </div>
      <div>
        <dt>P10 · P50 · P90</dt>
        <dd>Tiga kemungkinan dari model: P10 skenario kering, P50 perkiraan tengah, P90 skenario basah. Ini rentang kemungkinan, bukan ramalan pasti.</dd>
      </div>
      <div>
        <dt>Waspada · Siaga · Awas</dt>
        <dd>Ambang resmi riset ini: Waspada ≤ −1,0; Siaga ≤ −1,5; Awas ≤ −2,0. Makin negatif, makin kering.</dd>
      </div>
      <div>
        <dt>Rentang lebar</dt>
        <dd>Artinya model kurang yakin. Rentang sempit berarti antar-skenario saling berdekatan.</dd>
      </div>
      <div>
        <dt>MAE / RMSE</dt>
        <dd>Rata-rata selisih prakiraan terhadap kenyataan, dalam satuan SPEI. Makin kecil, makin dekat.</dd>
      </div>
    </dl>
  </details>
</template>
