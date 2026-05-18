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
    initial_sidebar_state="collapsed",
    menu_items={},
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 2.5rem; }
    /* Hide the sidebar toggle arrow entirely */
    [data-testid="collapsedControl"] { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Subspecies colour map ─────────────────────────────────────────────────────

SUBS_COLORS: dict[str, str] = {
    # Compound epithets checked before single words (longest-match logic)
    "camelopardalis camelopardalis": "#E6751A",
    "tippelskirchi tippelskirchi":   "#216DCC",
    "giraffa giraffa":               "#4D9C2C",
    # Unique single epithets
    "peralta":      "#DB0F0F",
    "antiquorum":   "#9A392B",
    "reticulata":   "#C41697",
    "thornicrofti": "#5BAED9",
    "angolensis":   "#457132",
}

SPECIES_FALLBACK: dict[str, str] = {
    "masai":       "#216DCC",
    "northern":    "#E6751A",
    "reticulated": "#C41697",
    "southern":    "#4D9C2C",
}

LEGEND_ENTRIES: list[tuple[str, str]] = [
    ("G. c. peralta",         "#DB0F0F"),
    ("G. c. camelopardalis",  "#E6751A"),
    ("G. c. antiquorum",      "#9A392B"),
    ("G. reticulata",         "#C41697"),
    ("G. t. tippelskirchi",   "#216DCC"),
    ("G. t. thornicrofti",    "#5BAED9"),
    ("G. g. giraffa",         "#4D9C2C"),
    ("G. g. angolensis",      "#457132"),
]

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

BASE_URL = (
    "https://raw.githubusercontent.com/"
    "Giraffe-Conservation-Foundation/GiraffaRange2025/main"
)
EXTENSIONS = [".shp", ".shx", ".dbf", ".prj", ".cpg"]


# ── Helpers ───────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_range(prefix: str) -> gpd.GeoDataFrame | None:
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
    return gdf.to_crs(epsg=6933).geometry.area.sum() / 1e6


def color_for_props(props: dict, fallback: str) -> str:
    candidates = [v.lower().strip() for v in props.values() if isinstance(v, str)]
    for key in sorted(SUBS_COLORS, key=len, reverse=True):
        for c in candidates:
            if key in c or c in key:
                return SUBS_COLORS[key]
    return fallback


def make_style(fallback: str):
    def _style(feature):
        color = color_for_props(feature.get("properties") or {}, fallback)
        return {"fillColor": color, "color": color, "weight": 1.2, "fillOpacity": 0.40}
    return _style


def make_highlight(fallback: str):
    def _hl(feature):
        color = color_for_props(feature.get("properties") or {}, fallback)
        return {"fillColor": color, "color": color, "weight": 2.5, "fillOpacity": 0.65}
    return _hl


def add_legend(fmap: folium.Map, entries: list[tuple[str, str]]) -> None:
    rows = "".join(
        f'<div style="display:flex;align-items:center;gap:7px;margin-bottom:5px">'
        f'<div style="width:13px;height:13px;border-radius:3px;flex-shrink:0;'
        f'background:{color};opacity:0.85"></div>'
        f'<span style="font-size:12px;font-style:italic;color:#222">{label}</span>'
        f'</div>'
        for label, color in entries
    )
    html = f"""
    <div style="
        position:fixed; bottom:30px; right:10px; z-index:1000;
        background:#ffffff !important; padding:10px 14px;
        border-radius:8px; box-shadow:0 2px 10px rgba(0,0,0,0.3);
        font-family:Arial,sans-serif; min-width:195px; border:1px solid #ccc;">
      <div style="font-weight:700;font-size:12px;margin-bottom:7px;
                  color:#111 !important;">Subspecies</div>
      {rows}
    </div>
    """
    fmap.get_root().html.add_child(folium.Element(html))


# ── Main ──────────────────────────────────────────────────────────────────────

st.markdown("### 🦒 Giraffa Range")

# Build map — no default tiles so LayerControl owns everything
m = folium.Map(location=[3, 30], zoom_start=4, tiles=None)

# Basemaps — first added = default shown (OpenStreetMap)
folium.TileLayer("OpenStreetMap",      name="Street (OSM)").add_to(m)
folium.TileLayer("CartoDB positron",   name="Light (CartoDB)").add_to(m)
folium.TileLayer("CartoDB dark_matter",name="Dark (CartoDB)").add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Tiles © Esri",
    name="Satellite (Esri)",
).add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Shaded_Relief/MapServer/tile/{z}/{y}/{x}",
    attr="Tiles © Esri",
    name="Terrain (Esri)",
).add_to(m)

# ── Protected Areas (WDPA) ────────────────────────────────────────────────────
# Uses the public UNEP-WCMC ArcGIS MapServer — no API key required.
# Source: https://gis.unep-wcmc.org/arcgis/rest/services/wdpa/public/MapServer
folium.WmsTileLayer(
    url="https://gis.unep-wcmc.org/arcgis/rest/services/wdpa/public/MapServer/WMSServer",
    layers="0",
    fmt="image/png",
    transparent=True,
    name="Protected Areas (WDPA)",
    show=False,
    opacity=0.35,
    attr=(
        "UNEP-WCMC and IUCN (2025), Protected Planet: The World Database "
        "on Protected Areas (WDPA). Cambridge, UK: UNEP-WCMC and IUCN. "
        "Available at: www.protectedplanet.net"
    ),
).add_to(m)

# Species layers
area_stats: dict[str, float] = {}

for name, cfg in SPECIES.items():
    with st.spinner(f"Loading {name}…"):
        gdf = load_range(cfg["prefix"])

    if gdf is None:
        st.warning(f"Could not load {name}. Check your connection.")
        continue

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
        show=True,
    ).add_to(m)

add_legend(m, LEGEND_ENTRIES)

# LayerControl — basemaps appear as radio, species as checkboxes
folium.LayerControl(collapsed=False, position="topright").add_to(m)

st_folium(m, height=640, use_container_width=True, returned_objects=[])

# ── Area stats ────────────────────────────────────────────────────────────────

if area_stats:
    st.divider()
    st.markdown("**Range area estimates**")
    cols = st.columns(len(area_stats))
    for col, (name, km2) in zip(cols, area_stats.items()):
        col.metric(label=name, value=f"{km2:,.0f} km²", help=SPECIES[name]["scientific"])

st.divider()
st.caption(
    "**Source:** Giraffe Conservation Foundation (2025). *Current distribution range of the four giraffe species.* "
    "[Download shapefiles](https://github.com/Giraffe-Conservation-Foundation/GiraffaRange2025)"
)
