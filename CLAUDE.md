# CLAUDE.md — Lagos Flood Hazard Web App (model bundle)

This folder is a **self-contained model bundle** copied from a larger flood-analysis project so
a web app can be built on a separate machine. You (Claude) are working **inside this folder only** —
the original analysis pipeline is NOT here, and you do **not** need it. Everything required is here.

---

## 1. What this project is

A final-year civil/environmental engineering project: **flood hazard mapping for Lagos State,
Nigeria** (student: Adeniyi Stephen Adeola). The full study already produced a flood hazard map,
population-exposure analysis, and a 31-year climate (NIMET) analysis. The analysis is **done** —
this bundle packages the finished models so they can be served interactively.

## 2. What we want to build

An interactive **web app — a flood hazard & exposure *explorer* with what-if scenarios.** Target
users: the student (to demo in their defense) and, conceptually, planners / emergency agencies
(LASEMA). Build it as **Streamlit** unless told otherwise (fastest path; `app_starter.py` is a
working skeleton — extend it, don't start from scratch).

Planned features (each maps to functions in `model_api.py` — all data is present):

1. **Hazard map** — render `flood_hazard_zones.tif` (5 zones) with LGA outlines (`lagos_lgas.geojson`).
2. **Point query** — user gives a Lagos location → hazard zone, elevation, slope, TWI, distance to
   river, runoff, and which LGA. → `point_query(lat, lon)`.
3. **Exposure dashboard** — rank all 20 LGAs by % population in High/Very High zones; statewide
   totals. → `exposure_by_lga()`, `real_baseline_exposure()`.
4. **Rainfall what-if scenario** — slider (% change) or a NIMET return-period storm (2/5/10/25/50/100-yr)
   → recompute the hazard map + projected exposure. → `scenario_exposure(scale)`, `recompute_hazard(scale)`,
   `design_rainfall(years)`.
5. **Climate panel** — show the 5 `fig_nimet_*.png` charts + a return-period calculator
   (`design_rainfall`, `return_period`).

Nice-to-haves later: a real slippy basemap (folium/leaflet) with click-to-query; downloadable
scenario maps; LULC urban-growth and sea-level scenarios (NOT in this bundle yet — see §7).

## 3. The single source of truth: `model_api.py`

Import it and call functions — **do not** re-implement the model. Key calls:

```python
import model_api as M
M.point_query(6.45, 3.40)        # dict: hazard_zone_name, elevation_m, runoff_depth_mm, lga, ...
M.design_rainfall(100)           # 3490.0 mm  (Gumbel 100-yr)
M.return_period(3932)            # ~289 yr
M.exposure_by_lga()              # DataFrame (20 LGAs)
M.exposure_by_zone()             # DataFrame (5 zones, exact totals)
M.real_baseline_exposure()       # dict: exact baseline people per zone
M.climatology()                  # DataFrame: 31-yr monthly rain/temp/RH
M.lga_boundaries()               # GeoDataFrame (WGS84)
exp, zones = M.scenario_exposure(1.3)   # +30% rainfall; exp[zone]={people,delta,pct_change}
M.recompute_hazard(scale)        # (fhi, zones, ref) for the scenario map
M.ZONE_NAMES, M.WEIGHTS          # constants
```

Verify it works first: `python model_api.py` (prints a self-test).

## 4. The models in the bundle

| Model | Files | Served by |
|-------|-------|-----------|
| Flood Hazard (AHP weighted overlay of 8 factors) | `core/flood_hazard_zones.tif`, `flood_hazard_index.tif`, `ahp_weights.txt` | `point_query`, `hazard_zones_array` |
| Population exposure | `core/exposure_by_lga.csv`, `exposure_by_zone.csv` | `exposure_by_*`, `real_baseline_exposure` |
| NIMET Gumbel return periods | `core/nimet_summary.json` | `design_rainfall`, `return_period` |
| NIMET climatology | `core/nimet_climatology.csv`, `nimet_annual_series.csv`, `fig_nimet_*.png` | `climatology` |
| Rainfall scenario (live recompute) | `factors/*` (8 factors + CN + base rainfall + WorldPop) | `recompute_hazard`, `scenario_exposure` |

`models/core/` (~29 MB) powers features 1–3 & 5. `models/factors/` (~284 MB) is **only** for the
rainfall scenario recompute (feature 4). If deploying display-only, you can omit `factors/`.

## 5. CRITICAL — honesty & framing (do not violate)

- **This is a hazard / exposure / scenario decision-support tool — NOT a flood forecast.** Never
  label it as predicting *when/whether* a specific future flood will happen; it shows where flooding
  is likely (susceptibility) and what-if scenarios, not dated predictions.
- **Scenario numbers are anchored.** Absolute exposure always starts from the exact validated
  baseline (`exposure_by_zone.csv`); the rainfall scenario applies the model's *relative* zone
  shift. Present the **% change / direction** as the headline, not tiny absolute diffs.
- **Rainfall effects are intentionally modest.** Rainfall drives only the runoff (0.12) + extreme-
  rainfall (0.08) factors = 0.20 of the index; elevation (0.20) + TWI (0.18) dominate. The map is
  topography-structured. This is correct, not a bug — explain it, don't "fix" it by over-weighting.
- The hazard model is an **AHP multi-criteria index**, not a calibrated physical/hydraulic model.
  The LULC input has ~53% accuracy; don't overstate precision.

## 6. Gotchas (will bite you if ignored)

- **Coordinates:** all public functions take **`lat, lon` (WGS84)**. Rasters are internally
  **EPSG:32631 (UTM 31N)**; `model_api` reprojects — don't pass UTM coords to `point_query`.
- **Windows installs:** `rasterio`/`geopandas` often fail via plain `pip`. Prefer
  `conda install -c conda-forge rasterio geopandas shapely streamlit`.
- **Never resample WorldPop counts onto a finer grid** — it inflates totals (~8×). `model_api`
  already avoids this (projects zones onto the native pop grid). Don't "simplify" that.
- **Lagos extent:** lon ≈ 2.7–4.4°E, lat ≈ 6.4–6.7°N. Queries outside return `null`/no LGA.
- **`flood_hazard_index.tif` is ~28 MB**; downsample for on-screen display (e.g. `out_shape=`),
  keep full-res only for point sampling.
- Scenario recompute caches static factors in `model_api._CACHE` — first scenario call is slow
  (~seconds), later ones fast. Don't clear the cache per request.

## 7. Out of scope for this app

Keep the app to the five features in §2. Not included and not needed here: the trained Random
Forest LULC classifier object (only its output raster is bundled), and any forecasting / real-time
capability.

## 8. Working agreement

- Reuse `model_api.py`; extend `app_starter.py`. Keep the app a thin UI over the API.
- Run `python model_api.py` after any change to the API to confirm it still passes the self-test.
- Match the existing concise, factual tone in any UI copy. Keep the honesty notes from §5 visible
  to end users (a short disclaimer line).
- Prefer the simplest thing that works (Streamlit widgets) over heavy custom frontend unless asked.
