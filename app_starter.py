"""
app_starter.py — minimal Streamlit demo of the Lagos Flood model API.
Run:  streamlit run app_starter.py
This is a STARTING POINT — extend it (proper basemap, click-to-query, styling) as you like.
"""
import numpy as np
import pandas as pd
import rasterio
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
import streamlit as st

import model_api as M

st.set_page_config(page_title="Lagos Flood Hazard Explorer", layout="wide")
st.title("Lagos Flood Hazard & Exposure Explorer")
st.caption("Decision-support tool (hazard + exposure + scenarios) — NOT a dated flood forecast.")

ZONE_COLORS = ["#ffffff", "#1a9850", "#a6d96a", "#fee08b", "#f46d43", "#a50026"]  # 0..5
CMAP = ListedColormap(ZONE_COLORS)
NORM = BoundaryNorm(range(7), CMAP.N)


def show_zones(zones, title):
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.imshow(zones, cmap=CMAP, norm=NORM)
    ax.set_title(title); ax.axis("off")
    handles = [plt.Rectangle((0, 0), 1, 1, color=ZONE_COLORS[i]) for i in range(1, 6)]
    ax.legend(handles, list(M.ZONE_NAMES.values()), loc="lower left", fontsize=7)
    st.pyplot(fig)


tab1, tab2, tab3, tab4 = st.tabs(
    ["🗺️ Hazard map", "📍 Point query", "👥 Exposure", "🌧️ Rainfall scenario"])

with tab1:
    st.subheader("Baseline flood hazard zones")
    with rasterio.open(M._core("flood_hazard_zones.tif")) as ds:
        zones = ds.read(1, out_shape=(ds.height // 4, ds.width // 4))   # downsampled
    show_zones(zones, "Lagos Flood Hazard Zones (AHP model)")

with tab2:
    st.subheader("Query any location in Lagos")
    c1, c2 = st.columns(2)
    lat = c1.number_input("Latitude", value=6.4550, format="%.4f")
    lon = c2.number_input("Longitude", value=3.4000, format="%.4f")
    if st.button("Query"):
        r = M.point_query(lat, lon)
        st.json(r)

with tab3:
    st.subheader("Population exposure by LGA")
    df = M.exposure_by_lga().sort_values("pct_high_very_high", ascending=False)
    st.bar_chart(df.set_index("lga_name")["pct_high_very_high"])
    st.dataframe(df, use_container_width=True)
    base = M.real_baseline_exposure()
    st.metric("People in High / Very High zones",
              f"{base['High+VeryHigh']:,.0f}",
              f"{100*base['High+VeryHigh']/base['total']:.1f}% of Lagos")

with tab4:
    st.subheader("Rainfall what-if scenario")
    mode = st.radio("Scenario by:", ["% change", "NIMET return-period storm"])
    if mode == "% change":
        pct = st.slider("Rainfall change (%)", -50, 100, 30, step=10)
        scale = 1 + pct / 100
        st.write(f"Rainfall × {scale:.2f}")
    else:
        T = st.select_slider("Return period (years)", [2, 5, 10, 25, 50, 100], value=100)
        design = M.design_rainfall(T)
        scale = design / 1822.0          # vs mean annual 1822 mm
        st.write(f"{T}-year design rainfall ≈ {design:,.0f} mm  →  ×{scale:.2f} of average")

    if st.button("Run scenario"):
        with st.spinner("Recomputing hazard + exposure..."):
            exp, zones = M.scenario_exposure(scale)
        hv = exp["High+VeryHigh"]
        st.metric("People in High / Very High zones (projected)",
                  f"{hv['people']:,.0f}", f"{hv['delta']:+,.0f} ({hv['pct_change']:+.1f}%)")
        show_zones(zones[::4, ::4], f"Hazard zones — rainfall ×{scale:.2f}")
        st.caption("Absolute numbers are anchored to the validated baseline; the scenario "
                   "applies the model's relative shift. Rainfall is 0.20 of the index weight, "
                   "so effects are modest — Lagos hazard is topography-dominated.")
