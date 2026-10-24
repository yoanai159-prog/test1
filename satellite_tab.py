"""Streamlit tab: real Sentinel-2 water surface as an independent check of reported fill."""
import json
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

from core.satellite import MESSAGES, consistency


def render(data_dir: Path):
    st.subheader("Satellite check (REAL Sentinel-2 data)")
    st.caption("This tab uses real satellite data for one reservoir. The other tabs use simulated data.")

    csv_path = data_dir / "satellite_observations.csv"
    if not csv_path.exists():
        st.info("No satellite data yet. Run `python satellite_update.py` once (needs internet) and reload.")
        return

    obs = pd.read_csv(csv_path).set_index("role")
    full, cur = obs.loc["full"], obs.loc["current"]

    c1, c2, c3 = st.columns(3)
    c1.metric(f"Full-pool area ({full.obs_date})", f"{full.water_area_km2:.2f} km²")
    c2.metric(f"Current area ({cur.obs_date})", f"{cur.water_area_km2:.2f} km²",
              f"{cur.water_area_km2 - full.water_area_km2:+.2f} km²")
    c3.metric("Current area as share of full", f"{cur.area_pct_of_full:.0f}%")

    layers = []
    for role, rgb in (("full", [40, 120, 220]), ("current", [240, 130, 30])):
        gj = json.loads((data_dir / f"satellite_water_{role}.geojson").read_text())
        layers.append(pdk.Layer("GeoJsonLayer", gj, stroked=True, filled=(role == "full"),
                                get_fill_color=rgb + [90], get_line_color=rgb + [255],
                                line_width_min_pixels=2))
    view = pdk.ViewState(latitude=float(cur.centroid_lat), longitude=float(cur.centroid_lon), zoom=11)
    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view, map_style=None))
    st.caption("Blue: water surface at full pool. Orange outline: water surface now.")

    st.markdown("**Cross-check against the fill reported by the operator**")
    reported = st.number_input("Reported fill (%)", 0.0, 100.0, 40.0, 1.0)
    tol = st.slider("Tolerance (percentage points of area)", 5, 30, 15)
    res = consistency(reported, float(cur.area_pct_of_full), float(tol))
    (st.success if res["status"] == "consistent" else st.warning)(MESSAGES[res["status"]])
    st.write(f"Reported fill {reported:.0f}% implies a water area of about **{res['expected_area_pct']:.0f}%** "
             f"of full; the satellite measures **{cur.area_pct_of_full:.0f}%** (gap {res['gap_pp']:+.0f} pp).")
    st.caption("Area is not volume. The conversion assumes volume ~ area^1.5 (illustrative); a real pilot "
               "uses the level-area-volume curve. Clouds, shadows and ice can make the area too small.")
