"""Streamlit demo: early warning for reservoirs and ranking of vulnerable settlements.

Run:  streamlit run app.py
All data are SIMULATED (see data/ and generate_data.py).
"""
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

from core.logic import ALERT_ORDER, Settings, explain, forecast, reservoir_status, settlement_risk
from satellite_tab import render as render_satellite

DATA = Path(__file__).parent / "data"

ALERT_RGB = {"green": [46, 160, 67], "yellow": [230, 190, 40], "orange": [240, 130, 30], "red": [210, 40, 40]}
RISK_RGB = {"low": [46, 160, 67], "medium": [240, 130, 30], "high": [210, 40, 40]}

st.set_page_config(page_title="Drought early warning (demo)", layout="wide")


@st.cache_data
def load():
    return (
        pd.read_csv(DATA / "reservoirs.csv"),
        pd.read_csv(DATA / "reservoir_observations.csv", parse_dates=["obs_date"]),
        pd.read_csv(DATA / "settlements.csv"),
        pd.read_csv(DATA / "supply_links.csv"),
    )


reservoirs, observations, settlements, links = load()

# ---- sidebar: tunable assumptions -------------------------------------------------
st.sidebar.header("Assumptions")
critical = st.sidebar.slider("Critical fill threshold (%)", 5, 40, 20)
window = st.sidebar.slider("Weeks used for the rate of decline", 2, 8, 4)
settings = Settings(critical_fill_pct=float(critical), window_weeks=int(window))
st.sidebar.caption(
    "Thresholds and weights are illustrative. In a pilot they are agreed with the operator, "
    "the water utility and the basin directorate."
)

# ---- compute -----------------------------------------------------------------------
status = {}
for _, r in reservoirs.iterrows():
    o = observations[observations["reservoir_id"] == r["reservoir_id"]]
    status[int(r["reservoir_id"])] = reservoir_status(o, r["total_capacity_m3"], settings)

alerts = {rid: s["alert_level"] for rid, s in status.items()}
weeks = {rid: s["weeks_to_threshold"] for rid, s in status.items()}
risk = settlement_risk(settlements, links, alerts, weeks, settings)

res_table = reservoirs.assign(
    alert=[alerts[int(i)] for i in reservoirs["reservoir_id"]],
    fill_pct=[round(status[int(i)]["fill_pct"], 1) for i in reservoirs["reservoir_id"]],
    norm_pct=[round(status[int(i)]["norm_pct"], 1) for i in reservoirs["reservoir_id"]],
    deviation_pp=[round(status[int(i)]["deviation_pp"], 1) for i in reservoirs["reservoir_id"]],
    decline_pp_week=[round(status[int(i)]["rate_pp_week"], 2) for i in reservoirs["reservoir_id"]],
    weeks_to_threshold=[
        None if weeks[int(i)] is None else round(weeks[int(i)], 1) for i in reservoirs["reservoir_id"]
    ],
)

# ---- header ------------------------------------------------------------------------

st.title("Drought early warning for reservoirs and settlements")
st.warning("Demo with SIMULATED data. Names, locations and numbers are invented. Not for operational use.")

cols = st.columns(len(ALERT_ORDER))
for c, level in zip(cols, ALERT_ORDER):
    c.metric(f"Reservoirs at {level}", int(sum(1 for a in alerts.values() if a == level)))

tab_map, tab_res, tab_set, tab_sat, tab_about = st.tabs(["Map", "Reservoirs", "Settlements at risk", "Satellite", "About"])
# ---- map ---------------------------------------------------------------------------

with tab_map:
    res_pts = res_table.assign(color=res_table["alert"].map(ALERT_RGB),
                               label="Reservoir " + res_table["name"] + " - alert: " + res_table["alert"])
    set_pts = risk.assign(color=risk["risk_class"].map(RISK_RGB),
                          label=risk["name"] + " - risk: " + risk["risk_class"])
    layers = [
        pdk.Layer("ScatterplotLayer", set_pts, get_position="[lon, lat]", get_fill_color="color",
                  get_radius=2500, pickable=True, opacity=0.8),
        pdk.Layer("ScatterplotLayer", res_pts, get_position="[lon, lat]", get_fill_color="color",
                  get_radius=5500, get_line_color=[20, 20, 20], line_width_min_pixels=2,
                  stroked=True, pickable=True, opacity=0.9),
    ]
    view = pdk.ViewState(latitude=42.7, longitude=25.2, zoom=7.4)
    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view,
                             tooltip={"text": "{label}"}))
    st.caption("Large rings: reservoirs coloured by alert level. Small dots: settlements coloured by risk class.")

# ---- reservoirs --------------------------------------------------------------------
with tab_res:
    st.dataframe(
        res_table[["name", "alert", "fill_pct", "norm_pct", "deviation_pp", "decline_pp_week", "weeks_to_threshold"]],
        use_container_width=True, hide_index=True,
    )
    pick = st.selectbox("Reservoir", reservoirs["name"])
    rid = int(reservoirs.loc[reservoirs["name"] == pick, "reservoir_id"].iloc[0])
    st_ = status[rid]
    o = observations[observations["reservoir_id"] == rid].sort_values("obs_date")
    left, right = st.columns(2)
    left.subheader("Fill and seasonal norm (%)")
    left.line_chart(o.set_index("obs_date")[["fill_pct", "season_norm_pct"]])
    fc = forecast(st_, horizon_weeks=8)
    right.subheader("Trend forecast with interval (%)")
    right.line_chart(fc.set_index("week_ahead")[["lower", "central", "upper"]])
    w = st_["weeks_to_threshold"]
    if w is None:
        st.info("The reservoir is not falling over the chosen window; no threshold crossing is expected.")
    else:
        lo, hi = st_["weeks_min"], st_["weeks_max"]
        hi_txt = "no upper bound" if hi is None else f"{hi:.1f}"
        st.write(
            f"**Alert: {st_['alert_level'].upper()}.** At {st_['rate_pp_week']:.2f} pp per week the reservoir "
            f"reaches {critical}% in about **{w:.1f} weeks** (range {lo:.1f} to {hi_txt} weeks). "
            "The forecast is a simple trend, not a hydrological model."
        )

# ---- settlements -------------------------------------------------------------------
with tab_set:
    show = risk[["rank", "name", "risk_class", "risk_score", "exposure_pct", "worst_reservoir_alert",
                 "weeks_to_threshold", "population"]]
    st.dataframe(show, use_container_width=True, hide_index=True)
    sel = st.selectbox("Explain a settlement", risk["name"])
    row = risk[risk["name"] == sel].iloc[0]
    st.info(explain(row))
    st.caption(
        "Score = 100 x exposure x (0.7 + 0.2 x population term + 0.1 x critical facility). "
        "Exposure = supply share x (1 - backup share) x alert factor (green 0, yellow 0.4, orange 0.7, red 1)."
    )
# ---- satellite ---------------------------------------------------------------------
with tab_sat:
    render_satellite(DATA)
# ---- about -------------------------------------------------------------------------
with tab_about:
    st.markdown(
        """
**What this demo shows.** A transparent chain from reservoir observations to a traffic light, a simple
trend with an interval, and a ranked list of settlements that depend on the reservoirs.

**What it does not do.** It does not use real data, and it is not a hydrological model. The language-model
step is replaced by a fixed template: an explanation may be reworded, but never changes numbers or classes.

**Next steps for a pilot.** Replace `data/` with real reservoir observations (Sentinel-1/2, operator data,
sensors), add the level-area-volume curve, and agree thresholds with the operator.

Data model: see `docs/data_schema.md`.
"""
    )
