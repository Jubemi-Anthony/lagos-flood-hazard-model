"""
model_api.py — Lagos Flood Hazard & Exposure Model API
=======================================================
A single, dependency-light Python module that loads the trained/produced models in
./models and exposes them as plain functions for a web app (Streamlit, FastAPI, Flask...).

Models exposed
--------------
1. Flood Hazard model (AHP weighted overlay)   -> point_query(), hazard_zone_image()
2. Population exposure model                    -> exposure_by_lga(), exposure_by_zone()
3. NIMET Gumbel return-period model             -> design_rainfall(), return_period()
4. NIMET climatology                            -> climatology()
5. Rainfall "what-if" scenario (recompute)      -> recompute_hazard(), scenario_exposure()

All rasters are EPSG:32631 (UTM Zone 31N). Coordinates passed in are lat/lon (WGS84).

NOTE on scope: this is a HAZARD / EXPOSURE / SCENARIO model (decision-support), NOT a
dated flood forecast. Scenario exposure numbers are approximate (use as relative deltas);
the exact baseline exposure is in models/core/exposure_by_lga.csv.
"""
import json
import math
import os

import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import reproject, Resampling, transform as warp_transform

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(HERE, "models", "core")
FACT = os.path.join(HERE, "models", "factors")


def _core(name): return os.path.join(CORE, name)
def _fact(name): return os.path.join(FACT, name)


# ───────────────────────── model constants (ported from flood_hazard_map.py) ──
WEIGHTS = {"elevation": 0.20, "twi": 0.18, "dist_rivers": 0.15, "flow_accum": 0.12,
           "runoff": 0.12, "slope": 0.10, "rainfall": 0.08, "lulc": 0.05}
INVERT = {"elevation": True, "twi": False, "dist_rivers": True, "flow_accum": False,
          "runoff": False, "slope": True, "rainfall": False, "lulc": False}
LULC_SCORE = {1: 0.90, 2: 0.30, 3: 0.10, 4: 0.70, 5: 0.75}   # 0 = nodata
ZONE_BREAKS = [0.0, 0.20, 0.40, 0.60, 0.80, 1.01]
ZONE_NAMES = {1: "Very Low", 2: "Low", 3: "Moderate", 4: "High", 5: "Very High"}

_NIMET = json.load(open(_core("nimet_summary.json"), encoding="utf-8"))
GUMBEL = _NIMET["gumbel"]            # {"mu":..., "beta":..., "return_levels": {...}}


# ════════════════════════════ 3. NIMET Gumbel return-period model ═════════════
def design_rainfall(return_period_years):
    """Return period (years) -> design annual rainfall depth (mm)."""
    mu, beta = GUMBEL["mu"], GUMBEL["beta"]
    yt = -math.log(-math.log(1 - 1.0 / return_period_years))
    return mu + beta * yt


def return_period(annual_rainfall_mm):
    """Annual rainfall (mm) -> estimated return period (years)."""
    mu, beta = GUMBEL["mu"], GUMBEL["beta"]
    z = (annual_rainfall_mm - mu) / beta
    F = math.exp(-math.exp(-z))
    return float("inf") if F >= 1 else 1.0 / (1.0 - F)


# ════════════════════════════ 2. Exposure + 4. Climatology ════════════════════
def exposure_by_lga():
    """DataFrame: per-LGA population by hazard zone + % in High/Very High."""
    return pd.read_csv(_core("exposure_by_lga.csv"))


def exposure_by_zone():
    """DataFrame: statewide population by hazard zone."""
    return pd.read_csv(_core("exposure_by_zone.csv"))


def climatology():
    """DataFrame: 31-yr NIMET monthly climatology (rain/temp/RH)."""
    return pd.read_csv(_core("nimet_climatology.csv"))


def lga_boundaries():
    """GeoDataFrame of the 20 Lagos LGA polygons (WGS84)."""
    import geopandas as gpd
    return gpd.read_file(_core("lagos_lgas.geojson"))


# ════════════════════════════ 1. Flood Hazard model — point query ═════════════
def _sample(path, lat, lon):
    if not os.path.exists(path):
        return None
    with rasterio.open(path) as ds:
        xs, ys = warp_transform("EPSG:4326", ds.crs, [lon], [lat])
        val = list(ds.sample([(xs[0], ys[0])]))[0][0]
        nd = ds.nodata
    if val is None or (nd is not None and val == nd) or not np.isfinite(val):
        return None
    return float(val)


def point_query(lat, lon):
    """Query every model layer at a lat/lon. Returns a dict ready to show in a popup."""
    out = {"lat": lat, "lon": lon}
    out["flood_hazard_index"] = _sample(_core("flood_hazard_index.tif"), lat, lon)
    z = _sample(_core("flood_hazard_zones.tif"), lat, lon)
    out["hazard_zone"] = int(z) if z else None
    out["hazard_zone_name"] = ZONE_NAMES.get(int(z)) if z else None
    out["elevation_m"] = _sample(_fact("dem.tif"), lat, lon)
    out["slope_deg"] = _sample(_fact("slope.tif"), lat, lon)
    out["twi"] = _sample(_fact("twi.tif"), lat, lon)
    out["distance_to_rivers_m"] = _sample(_fact("distance_to_rivers.tif"), lat, lon)
    out["runoff_depth_mm"] = _sample(_fact("runoff_depth_mm.tif"), lat, lon)
    out["lga"] = _lga_at(lat, lon)
    return out


def _lga_at(lat, lon):
    try:
        import geopandas as gpd
        from shapely.geometry import Point
    except ImportError:
        return None
    g = gpd.read_file(_core("lagos_lgas.geojson"))
    hit = g[g.contains(Point(lon, lat))]
    return None if hit.empty else str(hit.iloc[0].get("NAME_2"))


def hazard_zones_array():
    """Return (zones uint8 array, rasterio profile) for the BASELINE hazard map."""
    with rasterio.open(_core("flood_hazard_zones.tif")) as ds:
        return ds.read(1), ds.profile


# ════════════════════════════ 5. Rainfall scenario (recompute) ════════════════
_CACHE = {}   # cache aligned static factors so the slider stays responsive


def _ref_grid():
    with rasterio.open(_fact("dem.tif")) as ref:
        return {"crs": ref.crs, "transform": ref.transform,
                "width": ref.width, "height": ref.height}


def _aligned(path, ref, resampling=Resampling.bilinear):
    dst = np.full((ref["height"], ref["width"]), np.nan, dtype="float32")
    with rasterio.open(path) as src:
        reproject(source=rasterio.band(src, 1), destination=dst,
                  src_transform=src.transform, src_crs=src.crs,
                  dst_transform=ref["transform"], dst_crs=ref["crs"],
                  resampling=resampling)
        nd = src.nodata
    if nd is not None:
        dst[dst == nd] = np.nan
    return dst


def _normalize(arr, invert=False):
    lo, hi = np.nanpercentile(arr, 2), np.nanpercentile(arr, 98)
    if hi == lo:
        return np.zeros_like(arr)
    out = np.clip((arr - lo) / (hi - lo), 0, 1)
    return 1.0 - out if invert else out


def _scs_runoff(P, CN):
    S = 25400.0 / CN - 254.0
    return np.where(P > 0.2 * S, (P - 0.2 * S) ** 2 / (P + 0.8 * S), 0.0)


def _static_factors(ref):
    if "static" in _CACHE:
        return _CACHE["static"]
    flow = _aligned(_fact("flow_accumulation.tif"), ref)
    flow = np.where(flow > 0, np.log1p(flow), np.nan)
    lulc_raw = _aligned(_fact("lulc_10m.tif"), ref, Resampling.nearest)
    lulc = np.full_like(lulc_raw, np.nan)
    for cls, score in LULC_SCORE.items():
        lulc[lulc_raw == cls] = score
    s = {
        "elevation": _normalize(_aligned(_fact("dem.tif"), ref), True),
        "twi": _normalize(_aligned(_fact("twi.tif"), ref), False),
        "dist_rivers": _normalize(_aligned(_fact("distance_to_rivers.tif"), ref), True),
        "flow_accum": _normalize(flow, False),
        "slope": _normalize(_aligned(_fact("slope.tif"), ref), True),
        "lulc": lulc,
        "_CN": _aligned(_fact("curve_number.tif"), ref),
        "_P2021": _aligned(_fact("rainfall_total_2021.tif"), ref),
        "_rain95": _aligned(_fact("rainfall_95pct.tif"), ref),
    }
    _CACHE["static"] = s
    return s


def recompute_hazard(rainfall_scale=1.0):
    """Recompute the Flood Hazard Index + zones for a rainfall multiplier.
    rainfall_scale=1.0 reproduces the baseline; 1.3 = +30% rainfall, etc.
    Returns (fhi float array, zones uint8 array, ref grid dict)."""
    ref = _ref_grid()
    s = _static_factors(ref)
    runoff = _scs_runoff(s["_P2021"] * rainfall_scale, s["_CN"])
    norms = {
        "elevation": s["elevation"], "twi": s["twi"], "dist_rivers": s["dist_rivers"],
        "flow_accum": s["flow_accum"], "slope": s["slope"], "lulc": s["lulc"],
        "runoff": _normalize(runoff, False),
        "rainfall": _normalize(s["_rain95"] * rainfall_scale, False),
    }
    fhi = np.zeros((ref["height"], ref["width"]), dtype="float64")
    valid = None
    for name, norm in norms.items():
        lv = np.isfinite(norm)
        valid = lv if valid is None else (valid & lv)
        fhi += np.where(np.isfinite(norm), WEIGHTS[name] * norm, 0.0)
    fhi = np.where(valid, fhi, np.nan)
    zones = np.zeros(fhi.shape, dtype="uint8")
    for z in range(1, 6):
        zones[(fhi >= ZONE_BREAKS[z - 1]) & (fhi < ZONE_BREAKS[z]) & valid] = z
    return fhi, zones, ref


def real_baseline_exposure():
    """The EXACT, validated baseline exposure (from the original pipeline) — by zone."""
    z = pd.read_csv(_core("exposure_by_zone.csv"))
    d = {str(r["name"]).strip(): float(r["population"]) for _, r in z.iterrows()}
    d["High+VeryHigh"] = d.get("High", 0) + d.get("Very High", 0)
    d["total"] = sum(d[k] for k in ZONE_NAMES.values())
    return d


def _zone_pop_raw(rainfall_scale):
    """Population per zone from the live recompute (internally consistent, not the
    exact baseline). WorldPop is kept at native resolution; zones are projected onto it."""
    fhi, zones, ref = recompute_hazard(rainfall_scale)
    with rasterio.open(_fact("worldpop.tif")) as pop_ds:
        pop = pop_ds.read(1).astype("float64")
        nd = pop_ds.nodata
        valid = np.isfinite(pop) & (pop > 0)
        if nd is not None:
            valid &= (pop != nd)
        pop = np.where(valid, pop, 0.0)
        zop = np.zeros((pop_ds.height, pop_ds.width), dtype="uint8")
        reproject(source=zones, destination=zop,
                  src_transform=ref["transform"], src_crs=ref["crs"],
                  dst_transform=pop_ds.transform, dst_crs=pop_ds.crs,
                  resampling=Resampling.nearest)
    res = {ZONE_NAMES[z]: float(pop[zop == z].sum()) for z in range(1, 6)}
    res["High+VeryHigh"] = res["High"] + res["Very High"]
    return res, zones


def scenario_exposure(rainfall_scale=1.0):
    """Population exposure under a rainfall scenario, ANCHORED to the validated baseline.

    Absolute numbers always start from the exact original results; the rainfall scenario
    applies the model's *relative* zone shift on top. Returns (dict, zones_array) where
    dict[zone] = {people, delta, pct_change}. zone in {Very Low..Very High, High+VeryHigh}.
    """
    real = real_baseline_exposure()
    base_raw, zones = _zone_pop_raw(1.0)
    if abs(rainfall_scale - 1.0) < 1e-9:
        out = {k: {"people": real[k], "delta": 0.0, "pct_change": 0.0}
               for k in list(ZONE_NAMES.values()) + ["High+VeryHigh"]}
        return out, zones
    scn_raw, zones = _zone_pop_raw(rainfall_scale)
    out = {}
    for k in list(ZONE_NAMES.values()) + ["High+VeryHigh"]:
        ratio = (scn_raw[k] / base_raw[k]) if base_raw[k] > 0 else 1.0
        proj = real[k] * ratio
        out[k] = {"people": proj, "delta": proj - real[k],
                  "pct_change": 100.0 * (ratio - 1.0)}
    return out, zones


if __name__ == "__main__":
    print("Design rainfall, 100-yr:", round(design_rainfall(100)), "mm")
    print("Return period of 3932 mm:", round(return_period(3932)), "yr")
    print("Point query (Lagos Island ~6.45,3.40):")
    for k, v in point_query(6.45, 3.40).items():
        print(f"   {k}: {v}")
    b = scenario_exposure(1.0)[0]["High+VeryHigh"]
    s = scenario_exposure(1.3)[0]["High+VeryHigh"]
    print(f"Baseline High+VeryHigh: {b['people']:,.0f}")
    print(f"+30% rainfall High+VeryHigh: {s['people']:,.0f} "
          f"(delta {s['delta']:+,.0f}, {s['pct_change']:+.1f}%)")
