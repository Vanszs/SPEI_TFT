---
version: alpha
name: NusaPantau Kekeringan
description: Agricultural drought forecasting dashboard. Flat operational surfaces, one green accent, monospace data labels. Legibility over decoration.

colors:
  primary: "#263936"
  muted: "#687873"
  line: "#B9C7C2"
  green: "#0B6F68"
  soft-green: "#DCECE8"
  amber: "#9A5B00"
  red: "#A33D2E"
  blue: "#56708A"
  blue-soft: "#E7EEF0"
  neutral: "#F2F4EF"
  surface: "#FFFFFF"
  focus: "#246E62"

typography:
  h1:
    fontFamily: Inter
    fontSize: 2rem
    fontWeight: 600
    lineHeight: 1.12
    letterSpacing: "-0.01em"
  h2:
    fontFamily: Inter
    fontSize: 1.15rem
    fontWeight: 600
    lineHeight: 1.2
  body:
    fontFamily: Inter
    fontSize: 0.8125rem
    fontWeight: 400
    lineHeight: 1.6
  body-sm:
    fontFamily: Inter
    fontSize: 0.75rem
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: IBM Plex Mono
    fontSize: 0.625rem
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.07em"
  data-xl:
    fontFamily: IBM Plex Mono
    fontSize: 1.5rem
    fontWeight: 600
    lineHeight: 1.05
    letterSpacing: "-0.01em"
  data-md:
    fontFamily: IBM Plex Mono
    fontSize: 0.8125rem
    fontWeight: 600
    lineHeight: 1.2
  data-sm:
    fontFamily: IBM Plex Mono
    fontSize: 0.6875rem
    fontWeight: 500
    lineHeight: 1.2

rounded:
  xs: 4px
  sm: 8px
  md: 10px
  lg: 12px

spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px

components:
  card-prediction:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    rounded: "{rounded.lg}"
    padding: 16px
  card-prediction-featured:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    rounded: "{rounded.lg}"
    padding: 24px
  chip-normal:
    backgroundColor: "{colors.soft-green}"
    textColor: "{colors.green}"
    rounded: "{rounded.xs}"
    padding: 4px 8px
  chip-moderate:
    backgroundColor: "#FFF4D6"
    textColor: "{colors.amber}"
    rounded: "{rounded.xs}"
    padding: 4px 8px
  chip-severe:
    backgroundColor: "#F7E9E4"
    textColor: "{colors.red}"
    rounded: "{rounded.xs}"
    padding: 4px 8px
  chip-extreme:
    backgroundColor: "{colors.red}"
    textColor: "{colors.surface}"
    rounded: "{rounded.xs}"
    padding: 4px 8px
  button-primary:
    backgroundColor: "{colors.green}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    padding: 10px 14px
  button-primary-hover:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
  button-quiet:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    rounded: "{rounded.sm}"
    padding: 9px 13px
  button-quiet-hover:
    backgroundColor: "{colors.soft-green}"
    textColor: "{colors.green}"
  icon-button:
    backgroundColor: "{colors.soft-green}"
    textColor: "{colors.green}"
    rounded: "{rounded.sm}"
    size: 36px
  horizon-control:
    backgroundColor: "#EDF1ED"
    textColor: "{colors.primary}"
    rounded: "{rounded.md}"
    padding: 3px
  horizon-control-selected:
    backgroundColor: "{colors.green}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
  panel:
    backgroundColor: "#FBFCFA"
    textColor: "{colors.primary}"
    rounded: "{rounded.lg}"
    padding: 13px
---

## Overview

NusaPantau is an operational drought dashboard for five rice-growing regencies in East Java.
It reports a Pseudo-SPEI-3 forecast per regency from a Temporal Fusion Transformer, with
P10/P50/P90 uncertainty bands.

The interface is a **reading surface for numbers**, not a marketing page. Three rules drive
every choice:

1. **Data first.** The SPEI value and its uncertainty range are the largest, most contrasted
   elements on any card. Decoration never competes with them.
2. **Flat and dry.** Solid surfaces, hairlines, no gradients, no glass, no neon. The one
   atmospheric element — a soft shadow — exists only to separate a card from the desk surface.
3. **Monospace means measured.** Anything the model produced (SPEI, quantiles, RMSE, dates,
   grid ids) is set in IBM Plex Mono so a reader can tell a computed value from prose at a glance.

Agricultural severity has an established colour language: green is safe, amber is caution,
brick is danger. That mapping is used literally and nowhere else, so a colour never has to be
decoded.

## Colors

- **Ink (#263936) — primary.** A desaturated forest near-black, not pure grey. Body text and
  headlines. Chosen over `#000` so long paragraphs on the `#F2F4EF` ground stay soft.
- **Green (#0B6F68) — accent, 10% of any screen.** Field labels, active nav, primary button,
  focus ring. It is the only interactive colour; nothing else may be clickable-looking.
- **Amber (#9A5B00) / Red (#A33D2E) — severity only.** These two are reserved for `Waspada` and
  `Siaga`/`Awas`. They must never appear as generic emphasis, or the severity scale stops meaning
  anything. Amber-on-white uses a `#FFF4D6` ground to hold 4.5:1; red chips invert to white text.
- **Blue (#56708A) — observation.** Marks measured history and the P50 median so observed and
  forecast series are distinguishable without a legend lookup.
- **Neutral (#F2F4EF)** is the desk; **Surface (#FFFFFF)** is the paper. Cards are always white on
  the neutral ground — no tinted cards, which would flatten the severity chips into the surface.
- **Line (#B9C7C2)** is the only border colour. 1px, never 2px.

60-30-10 split: neutral ground reads as 60, white surface 30, green/severity 10.

## Typography

Two families, both already in the stack:

- **Inter** carries prose — descriptions, recommendations, section intros. Body sits at 13px/1.6
  with a 65ch measure; longer lines are the most common legibility failure in dashboards.
- **IBM Plex Mono** carries data and field labels. Its slightly wider digits keep tabular SPEI
  columns from shimmering when values change, and its distinct silhouette makes "this number came
  from the model" self-evident without a badge.

Weights are limited to three: 400 (prose), 500 (mono data), 600 (headings, labels, emphasis).
Eyebrow labels are 10px mono, `0.07em` tracking, uppercase — used once per section, never stacked.

Numbers are never set in Inter. A SPEI value in the prose face reads as decoration; in mono it
reads as a measurement.

## Layout

- A **fixed 72px left rail** holds navigation; content starts at `72px` and collapses to a
  full-width bar under the same top bar on narrow screens.
- **Container widths vary by content**: the card grid uses `min(1050px, 100% - 32px)`, the
  methodology text stops at `580px` so it stays readable, the detail chart is full-bleed within
  the grid. Uniform `max-w` on everything is the tell of a template.
- **The regency card grid is deliberately asymmetric.** Five regencies are not a 3-column grid.
  The most at-risk regency gets a **featured card that spans two columns and carries a larger
  median readout**; the other four flow in a single column beside it. This makes the ranking
  visible in the layout itself instead of only in the numbers.
- Cards are ordered by severity (Awas → Siaga → Waspada → Normal), not alphabetically. Alphabetical
  ordering is only appropriate when the reader is looking something up; here the reader needs to
  know where to act first.
- Spacing scale is contextual, not uniform: `4px` inside a chip, `8px` between a label and its
  value, `16px` inside a card, `24px` between cards, `32px` between sections.

## Elevation & Depth

Elevation is **flat by default**. Depth is used at exactly two levels and nowhere else:

- **Level 0 — flush.** Cards, panels, and rows sit on the ground with a 1px `line` border and no
  shadow. Most of the screen.
- **Level 1 — lifted.** Only the analysis drawer and the search dropdown lift, via
  `0 -8px 24px #2030260c` and `0 10px 25px #20302618`. A raised card competes with the data.

There is no glassmorphism, no backdrop blur except the app bar (`blur(10px)` at 93% opacity,
so scrolling content does not smear behind fixed navigation), and no coloured glow anywhere.

## Shapes

Radius is a **scale**, not one value:

- `4px` — severity chips, badges. Small enough that the chip still reads as a rectangle.
- `8px` — inputs, buttons, small controls.
- `10px` — grouped controls (the horizon stepper housing), zoom controls.
- `12px` — cards, panels, the map-free detail surface.

Nothing is `rounded-full`. A pill would soften the severity chips into buttons and blur the
line between a status label and an action.

## Forecast chart (30 hari)

Halaman utama adalah prakiraan **30 hari** — satu-satunya horizon yang model benar-benar
keluarkan (`MAX_PREDICTION_LENGTH = 30`). Tidak ada jalur 12 bulan.

- **Pita P10–P90** adalah elemen terbesar di kartu: ketidakpastian adalah isi utama, bukan hiasan.
  Median P50 digambar solid di atasnya, batas P10/P90 putus-putus.
- **Domain sumbu mengikuti data**, bukan tetap −2,5…1,5. Bila semua nilai positif, domain tetap
  membuat pita hanya setebal garis. Ambang kekeringan hanya digambar bila jatuh di dalam domain.
- **Satu angka acuan**, bukan seri observasi: "titik acuan observasi 0.17" sebagai garis putus-putus
  biru. Menambahkan 30 hari riwayat hanya mengecilkan bagian yang penting.
- **Bacaan per hari** untuk kursor dan keyboard (←/→/Home/End) dengan `aria-live="polite"`.
  Nilai per hari juga tersedia sebagai tabel yang dibuka lewat tombol, bukan selalu tampil.
- **viewBox berubah** pada ≤760px (420×260) supaya grafik tidak menjadi 98px tinggi di ponsel.

## Components

- **`card-prediction`** is the core unit: regency name, severity chip, current SPEI, the +N-month
  median, and the P10–P90 range as a horizontal band. Hover raises the border to accent and the
  shadow to `md` — it does **not** scale, so the grid never shifts under the cursor.
- **`card-prediction-featured`** is the same component with two columns of width and a larger
  `data-xl` median. One per grid, for the highest-severity regency.
- **`chip-*`** are the four severity states. They are labels, not buttons — no pointer cursor.
- **`button-primary`** is the single high-emphasis action in a view (open the report). Everything
  else is `button-quiet` or an `icon-button`.
- **`horizon-control`** is a segmented stepper (+1/+3/+6/+12 months). The selected segment uses the
  full accent fill; unselected segments stay text-only so the control has one focal point.
- **`panel`** is the low-contrast `#FBFCFA` surface for the forecast chart and the model-validation
  block, distinguishing supporting material from the white prediction cards.

## Do's and Don'ts

**Do**
- Put the SPEI median and its P10–P90 range on every card — an interval without context is a number,
  not a forecast.
- Order cards by severity and give the worst one more space.
- Keep one primary action per card (open detail); everything else is quiet.
- Set every computed value in IBM Plex Mono.
- Respect `prefers-reduced-motion: reduce` by removing the drawer and hover transitions.

**Don't**
- Don't tint prediction cards, and don't put a coloured left border on them.
- Don't use amber or red for anything except drought severity.
- Don't use a symmetric 3-column grid, gradient text, pill buttons, or emoji as icons.
- Don't scale cards on hover, and don't animate anything longer than 240ms.
- Don't show a coordinate pair or a grid-cell id on a prediction card — without a map they are
  noise.
- Don't present a placeholder value as a forecast; a missing prediction reads `—`, never `0.00`.
