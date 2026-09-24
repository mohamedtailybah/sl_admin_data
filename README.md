# Sierra Leone Administrative Boundaries — QGIS Plugin

**Author:** Mohamed Taily Bah

All boundary data ships **inside** the plugin as embedded shapefiles — once
installed, you don't need to source or load any external shapefiles.

## What's included

| Layer | Source | Features | Geometry |
|---|---|---|---|
| Regions | *derived* (see below) | 5 | Polygon |
| Districts | `data/district.shp` | 16 | Polygon |
| Chiefdoms | `data/chiefdoms.shp` | 205 | Polygon |
| Sections | `data/sections.shp` | 1,344 | Polygon |
| Forest Reserves | `data/forest_reserves.shp` | 27 | Polygon |
| Mangroves | `data/mangroves.shp` | 401 | Polygon |
| Lakes | `data/lakes.shp` | 99 | Polygon |
| Rivers | `data/rivers.shp` | 44 | Line |
| Roads | `data/roads.shp` | 323 | Line |
| Towns | `data/towns.shp` | 9,676 | Point |
| Major Towns | `data/major_towns.shp` | 75 | Point |

**Towns vs. Major Towns:** these are two different source datasets, not a
subset of one another. *Towns* is a dense OpenStreetMap-derived layer
(hamlets, villages, suburbs, cities). *Major Towns* is a separate, curated
NIMA settlement layer of 75 significant named towns with a `Province`
field - better suited when you just want the map to read cleanly at
country scale.

**A note on Forest Reserves' coordinates:** this layer's source shapefile
is in UTM Zone 28N rather than geographic WGS84 like the others. That's
fine - QGIS reprojects it on the fly using its own `.prj` file, so it
lines up correctly with everything else on the map without any conversion
needed on your end.

### A note on Regions

The Regions shapefile in the original dataset had no features in it (empty).
Rather than ship an empty layer, the plugin **derives Regions at runtime**
by dissolving the District polygons, grouped using the region name that's
already recorded against each Section (`Eastern`, `Northern`, `North
Western`, `Southern`, `Western`). This keeps the regions consistent with
the rest of the dataset without relying on a hand-maintained lookup table.
It also means Regions load a touch slower than the other layers the first
time, since the dissolve runs on the fly.

## Using the plugin

1. Install: copy the `sl_admin_boundaries` folder into your QGIS profile's
   `python/plugins` directory (see paths below), restart QGIS, and enable
   it under **Plugins → Manage and Install Plugins → Installed**.
2. Click the toolbar icon or **Sierra Leone Boundaries** menu entry.
3. For each boundary type (Regions, Districts, Chiefdoms, Sections, Towns):
   - Check **Show** to add it to the map.
   - Optionally pick a **Classify by** attribute to color the layer by
     category (e.g. color Districts by name, color Sections by their
     parent district, color Towns by settlement type).
   - Leave "single color" selected for a plain fill.
4. Pick a **color ramp** (or leave it on "Auto" for distinct per-category
   colors) and click **Apply**. You can keep adjusting and re-apply as
   often as you like — layers already on the map are re-styled in place
   rather than duplicated.

### Install paths

- **Windows:** `C:\Users\<you>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\`
- **macOS:** `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
- **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`

## Filtering Towns & Sections by Region or District

At the bottom of the dialog is a **"Show only Towns & Sections within a
Region or District"** panel:

1. Choose **Boundary type**: District or Region.
2. Choose the specific **Value** (e.g. "Bo" or "Southern").
3. Click **Apply filter**. This automatically shows the Sections and Towns
   layers if they weren't already on, restricts both to just the chosen
   boundary, and zooms the map to it. A status line reports how many
   sections and towns matched.
4. Click **Clear filter** at any time to go back to showing all sections
   and towns (the layers stay on the map, just unfiltered).

Two different techniques are used under the hood, because of what's
actually in the source data:

- **Sections** already carry their district (`FIRST_New1`) and region
  (`FIRST_Ne_2`) name directly as attributes, so this is a simple attribute
  filter.
- **Towns** have no district/region attribute in the source data at all —
  it's plain point data. So the plugin instead does a spatial test: it
  builds a spatial index over the 9,676 town points and checks which ones
  fall inside the chosen District polygon (or the chosen Region, i.e. the
  union of its districts).

Re-running **Apply** in the main boundary-layers panel afterwards won't
clear an active filter — it only touches layers that are freshly added,
so an already-filtered Sections/Towns layer keeps its filter while you
adjust colors elsewhere.

## Attribute reference

Some source fields had cryptic shapefile-truncated names; the plugin sets
friendlier aliases on load, but the underlying field names are unchanged
(useful if you're writing expressions or querying the attribute table):

- **Districts:** `DISTICT` – district name
- **Chiefdoms:** `FIRST_New_` – chiefdom name, `FIRST_FI_1` – parent district,
  `FIRST_FI_2` – headquarter town, `SUM_SUM__1` – total population,
  `SUM_SUM_Fi` – female population, `SUM_SUM_HO` – households
- **Sections:** `FIRST_SECT` – section name, `FIRST_New_` – parent chiefdom,
  `FIRST_New1` – parent district, `FIRST_Ne_2` – parent region,
  `SUM_Fina_1` – total population, `SUM_HOUSEH` – households
- **Towns:** `name` – settlement name, `fclass` – settlement type
  (city/town/village/hamlet/etc., from OpenStreetMap), `population`
- **Major Towns:** `NAM` – town name, `Province` – province name (a few
  entries have inconsistent capitalization/spelling in the source data,
  e.g. "Nothern Province" - left as-is rather than silently corrected)
- **Roads:** `RTT_DESCRI` – route type (Primary/Secondary/Unknown),
  `EXS_DESCRI` – operational status, `ACC_DESCRI` – positional accuracy
- **Rivers / Lakes:** `Name`, `CATCHM_LE1` – catchment classification level
- **Mangroves:** `Name` – cover type (values are inconsistently cased in
  the source, e.g. "Mangrove"/"mangrove"/"Swamp"/"swamp" - left as-is)
- **Forest Reserves:** `NAME`, `DISTRICT`, `Usage1`/`Usage2` – designated
  use, `Year_Const` – year the reserve was constituted

A few statistical fields (e.g. `SUM_New_SC` on Chiefdoms) come straight
from the source data with unclear original meaning and were left as-is
rather than guessed at — worth confirming against your source if you need
them.

## Possible extensions

- Extend the Region/District filter to the new layers too (e.g. "only
  show roads within this district").
- National Parks data is available in the same source package but wasn't
  requested yet - happy to add it as another polygon layer alongside
  Forest Reserves.
- Graduated (numeric) classification for the population/household fields,
  in addition to the current categorical classification.
- A "zoom to layer" button per row.
- Label toggles (e.g. show district/section/river names on the map).

Happy to add any of these — just ask.
