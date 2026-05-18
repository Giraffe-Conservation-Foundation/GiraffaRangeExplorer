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

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Giraffa Range",
    page_icon="🦒",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    "<style>.block-container { padding-top: 1.5rem; }</style>",
    unsafe_allow_html=True,
)

# ── Subspecies colour map ─────────────────────────────────────────────────────
# Keyed by lowercase fragments that uniquely identify each subspecies.
# The lookup tries longest-match first to avoid "camelopardalis" swallowing
# "camelopardalis camelopardalis" etc.

SUBS_COLORS: dict[str, str] = {
    # Full trinomials (checked first)
    "camelopardalis camelopardalis": "#E6751A",
    "tippelskirchi tippelskirchi":   "#216DCC",
    "giraffa giraffa":               "#4D9C2C",
    # Unique epithets
    "peralta":      "#DB0F0F",
    "antiquorum":   "#9A392B",
    "reticulata":   "#C41697",
    "thornicrofti": "#5BAED9",
    "angolensis":   "#457132",
}

# Species fallback colours (used when no subspecies match is found)
SPECIES_FALLBACK: dict[str, str] = {
    "masai":       "#216DCC",
    "northern":    "#E6751A",
    "reticulated": "#C41697",
    "southern":    "#4D9C2C",
}

# Legend entries: label → colour
LEGEND_ENTRIES: list[tuple[str, str]] = [
    ("G. c. peralta",                   "#DB0F0F"),
    ("G. c. camelopardalis",            "#E6751A"),
    ("G. c. antiquorum",                "#9A392B"),
    ("G. reticulata",                   "#C41697"),
    ("G. t. tippelskirchi",             "#216DCC"),
    ("G. t. thornicrofti",              "#5BAED9"),
    ("G. g. giraffa",                   "#4D9C2C"),
    ("G. g. angolensis",                "#457132"),
]

# ── Species configuration ─────────────────────────────────────────────────────

SPECIES: dict[str, dict] = {
    "Masai Giraffe": {
        "scientific": "Giraffa tippelskirchi",
        "prefix":     "masai",
    },
    "Northern Giraffe": {
        "scientific": "Giraffa camelopardalis",
        "prefix":     "northern",
    },
    "Reticulated Giraffe": {
        "scientific": "Giraffa reticulata",
        "prefix":     "reticulated",
    },
    "Southern Giraffe": {
        "scientific": "Giraffa giraffa",
        "prefix":     "southern",
    },
}

# ── Basemap options ───────────────────────────────────────────────────────────

BASEMAPS: dict[str, dict] = {
    "Light (CartoDB)": {
        "tiles": "CartoDB positron",
        "attr":  "",
    },
    "Dark (CartoDB)": {
        "tiles": "CartoDB dark_matter",
        "attr":  "",
    },
    "Street (OpenStreetMap)": {
        "tiles": "OpenStreetMap",
        "attr":  "",
    },
    "Satellite (Esri)": {
        "tiles": (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        "attr": "Tiles © Esri",
    },
    "Terrain (Esri)": {
        "tiles": (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Shaded_Relief/MapServer/tile/{z}/{y}/{x}"
        ),
        "attr": "Tiles © Esri",
    },
}

BASE_URL = (
    "https://raw.githubusercontent.com/"
    "Giraffe-Conservation-Foundation/GiraffaRange2025/main"
)
EXTENSIONS = [".shp", ".shx", ".dbf", ".prj", ".cpg"]


# ── Helpers ───────────────────────────────────────────────────────────────────

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
                pass

        shp_path = os.path.join(tmpdir, "range.shp")
        if not os.path.exists(shp_path):
            return None
        try:
            gdf = gpd.read_file(shp_path)
            return gdf.to_crs(epsg=4326)
        except Exception:
            return None


def area_km2(gdf: gpd.GeoDataFrame) -> float:
    gdf_proj = gdf.to_crs(epsg=6933)
    return gdf_proj.geometry.area.sum() / 1e6


def color_for_properties(props: dict, fallback: str) -> str:
    """
    Scan all string properties of a GeoJSON feature and return the matching
    subspecies colour. Tries longest keys first to avoid partial collisions.
    """
    candidates: list[str] = []
    for v in props.values():
        if isinstance(v, str):
            candidates.append(v.lower().strip())

    # Sort keys longest-first so compound epithets beat single-word ones
    for key in sorted(SUBS_COLORS, key=len, reverse=True):
        for candidate in candidates:
            if key in candidate or candidate in key:
                return SUBS_COLORS[key]

    return fallback


def make_style(fallback: str):
    """Return a folium style_function that colours by subspecies."""
    def _style(feature):
        color = color_for_properties(
            feature.get("properties") or {}, fallback
        )
        return {
            "fillColor": color,
            "color":     color,
            "weight":    1.2,
            "fillOpacity": 0.40,
        }
    return _style


def make_highlight(fallback: str):
    def _highlight(feature):
        color = color_for_properties(
            feature.get("properties") or {}, fallback
        )
        return {
            "fillColor": color,
            "color":     color,
            "weight":    2.5,
            "fillOpacity": 0.65,
        }
    return _highlight


def add_legend(fmap: folium.Map, entries: list[tuple[str, str]]) -> None:
    """Inject a simple HTML legend into the folium map."""
    rows = "".join(
        f'<div style="display:flex;align-items:center;gap:7px;margin-bottom:4px">'
        f'<div style="width:14px;height:14px;border-radius:3px;'
        f'background:{color};opacity:0.85;flex-shrink:0"></div>'
        f'<span style="font-size:12px;font-style:italic">{label}</span></div>'
        for label, color in entries
    )
    legend_html = f"""
    <div style="
        position: fixed; bottom: 30px; right: 10px; z-index: 1000;
        background: rgba(255,255,255,0.92); padding: 10px 14px;
        border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.25);
        font-family: sans-serif; min-width: 190px;">
      <div style="font-weight:700;font-size:12px;margin-bottom:6px">Subspecies</div>
      {rows}
    </div>
    """
    fmap.get_root().html.add_child(folium.Element(legend_html))


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🦒 Giraffa Range")
    st.caption("Current (2025) distribution maps for the four giraffe species")
    st.divider()

    st.markdown("**Show species**")
    selected: dict[str, bool] = {}
    for name in SPECIES:
        selected[name] = st.checkbox(name, value=True, key=f"chk_{name}")

    st.divider()

    st.markdown("**Basemap**")
    basemap_choice = st.selectbox(
        "Basemap",
        options=list(BASEMAPS.keys()),
        index=0,
        label_visibility="collapsed",
    )

    st.divider()
    st.caption(
        "Data: [GCF GiraffaRange2025](https://github.com/Giraffe-Conservation-Foundation/GiraffaRange2025)  \n"
        "© Giraffe Conservation Foundation"
    )


# ── Main area ─────────────────────────────────────────────────────────────────

st.markdown("### Range Explorer")
st.caption("Toggle species · change basemap · click a polygon for attributes · scroll to zoom.")

bm = BASEMAPS[basemap_choice]
m = folium.Map(
    location=[3, 30],
    zoom_start=4,
    tiles=bm["tiles"],
    attr=bm["attr"],
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

    tooltip_fields = [c for c in gdf.columns if c.lower() != "geometry"][:6]
    fallback = SPECIES_FALLBACK[cfg["prefix"]]

    folium.GeoJson(
        data=gdf.__geo_interface__,
        name=name,
        style_function=make_style(fallback),
        highlight_function=make_highlight(fallback),
        tooltip=(
            folium.GeoJsonTooltip(fields=tooltip_fields, localize=True)
            if tooltip_fields else None
        ),
        popup=(
            folium.GeoJsonPopup(fields=tooltip_fields)
            if tooltip_fields else None
        ),
    ).add_to(m)

add_legend(m, LEGEND_ENTRIES)
folium.LayerControl(collapsed=False).add_to(m)

st_folium(m, height=600, use_container_width=True, returned_objects=[])

# ── Area statistics ───────────────────────────────────────────────────────────

if area_stats:
    st.divider()
    st.markdown("**Range area estimates**")
    cols = st.columns(len(area_stats))
    for col, (name, km2) in zip(cols, area_stats.items()):
        col.metric(
            label=name,
            value=f"{km2:,.0f} km²",
            help=SPECIES[name]["scientific"],
        )
elif not any(selected.values()):
    st.info("Select at least one species in the sidebar to display its range.")
