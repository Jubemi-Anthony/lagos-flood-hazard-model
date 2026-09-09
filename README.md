# Lagos Flood Hazard & Exposure — Model Bundle

Everything needed to build a web app on **another PC**, with no re-analysis required.
All models are already trained/produced; this bundle wraps them behind one Python module
(`model_api.py`). Copy this whole folder to the other machine.

> **Scope (be honest in your app):** this is a **hazard / exposure / scenario** decision-support
> tool — **not** a dated flood *forecast*. It shows where flooding is likely and what-if scenarios.

---

## 1. What's inside

```
flood_model_bundle/
├── model_api.py          ← THE API. Import this; call its functions.
├── app_starter.py        ← Minimal Streamlit demo (run it, then extend).
├── requirements.txt
├── README.md             ← this file
└── models/
    ├── core/             (~29 MB)  — needed for the DISPLAY tabs
    │   ├── flood_hazard_zones.tif      5-class hazard map (the main deliverable)
    │   ├── flood_hazard_index.tif      continuous 0–1 hazard index
    │   ├── ahp_weights.txt             the model's AHP weights
    │   ├── exposure_by_lga.csv         exact population exposure, all 20 LGAs
    │   ├── exposure_by_zone.csv        exact statewide exposure by zone
    │   ├── lagos_lgas.geojson          20 LGA polygons (WGS84) for the map
    │   ├── nimet_summary.json          Gumbel return-period model params
    │   ├── nimet_climatology.csv       31-yr monthly climate
    │   ├── nimet_annual_series.csv     annual rainfall/temp/humidity series
    │   └── fig_nimet_*.png             5 ready-made NIMET charts
    └── factors/          (~284 MB) — only needed for the RAINFALL SCENARIO tab
        ├── dem.tif, slope.tif, twi.tif, distance_to_rivers.tif,
        │   flow_accumulation.tif, lulc_10m.tif      (static conditioning factors)
        ├── curve_number.tif, rainfall_total_2021.tif, rainfall_95pct.tif,
        │   runoff_depth_mm.tif                       (rainfall-driven factors)
        └── worldpop.tif                              (population, for scenario exposure)
```

If you only want the display features, you can copy **just `models/core/`** (29 MB) and skip
the 284 MB `factors/` folder. The scenario tab needs `factors/`.

---

## 2. The models (and the functions that expose them)

| # | Model | What it does | Functions in `model_api.py` |
|---|-------|--------------|------------------------------|
| 1 | **Flood Hazard** (AHP weighted overlay of 8 factors) | where Lagos is flood-prone | `point_query(lat, lon)`, `hazard_zones_array()` |
| 2 | **Population exposure** | people per hazard zone / LGA | `exposure_by_lga()`, `exposure_by_zone()`, `real_baseline_exposure()` |
| 3 | **NIMET Gumbel return-period** | design rainfall for a return period | `design_rainfall(years)`, `return_period(mm)` |
| 4 | **NIMET climatology** | 31-yr seasonal cycle | `climatology()` |
| 5 | **Rainfall scenario (live recompute)** | new map + exposure if rainfall changes | `recompute_hazard(scale)`, `scenario_exposure(scale)` |

Helpers: `lga_boundaries()` (GeoDataFrame), `ZONE_NAMES`, `WEIGHTS`.

---

## 3. Quick start (on the other PC)

```bash
cd flood_model_bundle
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r requirements.txt

python model_api.py          # sanity check — prints design rainfall, a point query, a scenario
streamlit run app_starter.py # opens the demo app in your browser
```

> **Installing `rasterio` / `geopandas` on Windows:** easiest via conda
> (`conda install -c conda-forge rasterio geopandas streamlit`) if `pip` gives wheel errors.

### Minimal usage in your own code
```python
import model_api as M

M.design_rainfall(100)            # -> 3490.0  (mm, 100-yr storm)
M.point_query(6.45, 3.40)         # -> {hazard_zone_name: 'Moderate', elevation_m: 7.2, lga: 'LagosIsland', ...}
M.exposure_by_lga()               # -> DataFrame, 20 LGAs
exp, zones = M.scenario_exposure(1.3)   # +30% rainfall
exp["High+VeryHigh"]              # -> {'people': 4827500, 'delta': +17431, 'pct_change': +0.4}
```

---

## 4. What the app can do (all from this bundle)

1. **Hazard map** — show `flood_hazard_zones.tif` colored by 5 zones + LGA outlines.
2. **Point query** — type/click a location → hazard zone, elevation, runoff, distance to river, LGA.
3. **Exposure dashboard** — rank 20 LGAs by % exposed; statewide totals (4.81 M in High/Very High).
4. **Rainfall scenario** — slider or NIMET return-period storm → recompute map + projected exposure.
5. **Climate panel** — show the 5 `fig_nimet_*.png` charts + a return-period calculator.

---

## 5. Important notes / honesty

- **Coordinates:** functions take `lat, lon` (WGS84). All rasters are EPSG:32631 internally;
  `model_api` reprojects for you.
- **Scenario exposure is anchored:** absolute numbers always start from the exact validated
  baseline (`exposure_by_zone.csv`); the rainfall scenario applies the model's *relative* zone
  shift on top. Trust the **direction and % change** more than tiny absolute differences.
- **Why rainfall effects look modest:** rainfall drives only the runoff + extreme-rainfall
  factors (0.20 of the 1.0 index weight); elevation + TWI dominate (0.38). Lagos flood hazard is
  topography-structured — the model correctly reflects that.
- **Deployment:** for a public host (Streamlit Cloud / Render), the 284 MB `factors/` folder is
  large — either deploy display-only (core, 29 MB) or use Git LFS / external storage for factors.
- **Not in this bundle:** the trained Random Forest LULC classifier object (only its output
  raster is here). Serving live pixel classification would need the model re-saved from
  `lulc_classification.py`.
