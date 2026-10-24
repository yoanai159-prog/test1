# Adding the satellite layer to test1

1. Copy `core/satellite.py`, `satellite_update.py`, `satellite_tab.py`, `requirements-satellite.txt`
   and `tests/test_satellite.py` into the repo (same folders).
2. In `app.py` add `from satellite_tab import render as render_satellite`, then change the tabs line to:
   `tab_map, tab_res, tab_set, tab_sat, tab_about = st.tabs(["Map", "Reservoirs", "Settlements at risk", "Satellite", "About"])`
   and add:
   `with tab_sat:\n    render_satellite(DATA)`
3. Run once (internet): `pip install -r requirements-satellite.txt && python satellite_update.py`
   and COMMIT the files it writes in `data/` so the demo works offline.
4. `pytest` should now include the new tests (they need no rasterio).
