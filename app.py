"""
Giraffa Range — Streamlit app
Explore the 2025 distribution range maps of the four giraffe species.
Data source: https://github.com/Giraffe-Conservation-Foundation/GiraffaRange2025
"""

import os
import tempfile

import folium
import geopandas as gpd
import requests
import streamlit as st
from streamlit_folium import st_folium

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Giraffa Range",
    page_icon="🦒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling ───────────────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    /* Hide Streamlit default top padding */
    .block-container { padding-top: 1.5rem; }

    /* Species card */
    .species-card {
        border-left: 4px solid var(--card-color);
        padding: 0.6rem 0.8rem;
        margin-bottom: 0.8rem;
        border-radius: 0 6px 6px 0;
        background: rgba(255,255,255,0.05);
    }
    .species-name  { font-weight: 700; font-size: 0.95rem; margin: 0; }
    .species-sci   { font-style: italic; font-size: 0.78rem; opacity: 0.75; margin: 0; }
    .species-badge {
        display: inline-block;
        font-size: 0.7rem;
        font-weight: 600;
        padding: 1px 7px;
        border-radius: 10px;
        margin-top: 4px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Species configuration ─────────────────────────────────────────────────────

SPECIES = {
    "Masai Giraffe": {
        "scientific": "Giraffa tippelskirchi",
        "prefix": "masai",
        "color": "#E87722",      # GCF orange
        "status": "Vulnerable",
        "status_bg": "#F5A623",
        "status_text": "#000",
        "description": (
            "The most numerous giraffe species, found in Tanzania and Kenya. "
            "Population declined ~32% over the last three decades."
        ),
    },
    "Northern Giraffe": {
        "scientific": "Giraffa camelopardalis",
        "prefix": "northern",
        "color": "#C0392B",      # red
        "status": "Vulnerable",
        "status_bg": "#E74C3C",
        "status_text": "#fff",
        "description": (
            "The rarest species, with fewer than 6,000 individuals in fragmented "
            "populations across Central and West Africa."
        ),
    },
    "Reticulated Giraffe": {
        "scientific": "Giraffa reticulata",
        "prefix": "reticulated",
        "color": "#2471A3",      # blue
        "status": "Endangered",
        "status_bg": "#D35400",
        "status_text": "#fff",
        "description": (
            "Recognisable by its large, clearly defined patches. Found in "
            "north-eastern Kenya, southern Ethiopia, and Somalia."
        ),
    },
    "Southern Giraffe": {
        "scientific": "Giraffa giraffa",
        "prefix": "southern",
        "color": "#1E8449",      # green
        "status": "Least Concern",
        "status_bg": "#27AE60",
        "status_text": "#fff",
        "description": (
            "The most stable population, distributed across southern African "
            "countries including Namibia, Botswana, Zimbabwe, and South Africa."
        ),
    },
}

BASE_URL = (
    "https://raw.githubusercontent.com/"
    "Giraffe-Conservation-Foundation/GiraffaRange2025/main"
)
EXTENSIONS = [".shp", ".shx", ".dbf", ".prj", ".cpg"]


# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_range(prefix: str) -> gpd.GeoDataFrame | None:
    """Download shapefile components from GitHub and return a GeoDataFrame."""
    with tempfile.TemporaryDirectory() as tmpdir:
        for ext in EXTENSIONS:
            url = f"{BASE_URL}/Range_{prefix}_2025{ext}"
            try:
                r = requests.get(url, timeout=30)
                r.raise_for_status()
                with open(os.path.join(tmpdir, f"range{ext}"), "wb") as fh:
                    fh.write(r.content)
            except requests.RequestException:
                pass  # optional files (.cpg) may not exist; continue

        shp_path = os.path.join(tmpdir, "range.shp")
        if not os.path.exists(shp_path):
            return None
        try:
            gdf = gpd.read_file(shp_path)
            return gdf.to_crs(epsg=4326)
        except Exception:
            return None


def area_km2(gdf: gpd.GeoDataFrame) -> float:
    """Return total area in km²."""
    gdf_proj = gdf.to_crs(epsg=6933)   # equal-area projection
    return gdf_proj.geometry.area.sum() / 1e6


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🦒 Giraffa Range")
    st.caption("Current (2025) distribution maps for the four giraffe species")
    st.divider()

    st.markdown("**Show species on map**")
    selected = {}
    for name, cfg in SPECIES.items():
        selected[name] = st.checkbox(name, value=True, key=f"chk_{name}")

    st.divider()

    # Species info cards for checked species
    for name, cfg in SPECIES.items():
        if not selected[name]:
            continue
        st.markdown(
            f"""
            <div class="species-card" style="--card-color:{cfg['color']}">
              <p class="species-name" style="color:{cfg['color']}">{name}</p>
              <p class="species-sci">{cfg['scientific']}</p>
              <span class="species-badge"
                    style="background:{cfg['status_bg']};color:{cfg['status_text']}">
                {cfg['status']}
              </span>
              <p style="font-size:0.78rem;margin-top:6px;opacity:0.85">{cfg['description']}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()
    st.caption(
        "Data: [GCF GiraffaRange2025](https://github.com/Giraffe-Conservation-Foundation/GiraffaRange2025)  \n"
        "© Giraffe Conservation Foundation"
    )


# ── Main area ─────────────────────────────────────────────────────────────────

st.markdown("### Range Explorer")
st.caption(
    "Toggle species in the sidebar. Click any polygon for attributes. "
    "Scroll or pinch to zoom."
)

# Load data and build map
m = folium.Map(
    location=[3, 30],
    zoom_start=4,
    tiles="CartoDB positron",
    width="100%",
)

any_loaded = False
area_stats: dict[str, float] = {}

for name, cfg in SPECIES.items():
    if not selected[name]:
        continue

    with st.spinner(f"Loading {name}…"):
        gdf = load_range(cfg["prefix"])

    if gdf is None:
        st.warning(f"Could not load data for {name}. Check your internet connection.")
        continue

    any_loaded = True
    area_stats[name] = area_km2(gdf)

    # Build tooltip fields from available columns
    tooltip_fields = [c for c in gdf.columns if c.lower() != "geometry"][:5]

    folium.GeoJson(
        data=gdf.__geo_interface__,
        name=name,
        style_function=lambda _f, c=cfg["color"]: {
            "fillColor": c,
            "color": c,
            "weight": 1.2,
            "fillOpacity": 0.35,
        },
        highlight_function=lambda _f, c=cfg["color"]: {
            "fillColor": c,
            "color": c,
            "weight": 2.5,
            "fillOpacity": 0.6,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=tooltip_fields,
            localize=True,
        ) if tooltip_fields else None,
        popup=folium.GeoJsonPopup(fields=tooltip_fields) if tooltip_fields else None,
    ).add_to(m)

folium.LayerControl(collapsed=False).add_to(m)

# Render map
st_folium(m, height=580, use_container_width=True, returned_objects=[])

# ── Area statistics ───────────────────────────────────────────────────────────

if area_stats:
    st.divider()
    st.markdown("**Range area estimates**")
    cols = st.columns(len(area_stats))
    for col, (name, km2) in zip(cols, area_stats.items()):
        cfg = SPECIES[name]
        col.metric(
            label=name,
            value=f"{km2:,.0f} km²",
            help=f"{cfg['scientific']}",
        )

elif not any(selected.values()):
    st.info("Select at least one species in the sidebar to display its range.")
