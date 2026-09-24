"""
boundary_data.py

Loads the Sierra Leone administrative and thematic layers that are embedded
inside this plugin (no external shapefiles needed), and provides helpers
for color classification.

Administrative hierarchy: Region > District > Chiefdom > Section.
Thematic layers: Towns / Major Towns (points), Roads / Rivers (lines),
Lakes / Mangroves / Forest Reserves (polygons).

Note on Regions: the source dataset's Regions shapefile ships with zero
features, so the Regions layer is instead *derived* at runtime by dissolving
the District polygons according to the Region <-> District relationship
that already exists in the Sections data (field FIRST_Ne_2 = region name,
FIRST_New1 = district name for each section). This keeps the derived
regions consistent with the rest of the dataset instead of relying on a
hard-coded, hand-maintained mapping.
"""

import os
import random
from collections import defaultdict

from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsSymbol,
    QgsWkbTypes,
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsSingleSymbolRenderer,
    QgsStyle,
    QgsSpatialIndex,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# ---------------------------------------------------------------------------
# Layer catalogue
# ---------------------------------------------------------------------------
# key: internal identifier used throughout the plugin
# label: shown to the user
# file: shapefile inside data/ (None for the derived Regions layer)
# default_color: fallback solid color when no classification is chosen
# classify_fields: list of (field_name, display_label) offered in the
#                   "classify by" dropdown - curated to categorical fields
#                   that make sense to color by.
LAYER_DEFS = {
    "regions": {
        "label": "Regions",
        "file": None,
        "geometry": "polygon",
        "default_color": "#2C6E8F",
        "classify_fields": [("REGION", "Region name")],
    },
    "districts": {
        "label": "Districts",
        "file": "district.shp",
        "geometry": "polygon",
        "default_color": "#5E7A50",
        "classify_fields": [("DISTICT", "District name")],
    },
    "chiefdoms": {
        "label": "Chiefdoms",
        "file": "chiefdoms.shp",
        "geometry": "polygon",
        "default_color": "#9C7C3C",
        "classify_fields": [
            ("FIRST_New_", "Chiefdom name"),
            ("FIRST_FI_1", "Parent district"),
        ],
    },
    "sections": {
        "label": "Sections",
        "file": "sections.shp",
        "geometry": "polygon",
        "default_color": "#7A4B8F",
        "classify_fields": [
            ("FIRST_SECT", "Section name"),
            ("FIRST_New_", "Parent chiefdom"),
            ("FIRST_New1", "Parent district"),
            ("FIRST_Ne_2", "Parent region"),
        ],
    },
    "towns": {
        "label": "Towns",
        "file": "towns.shp",
        "geometry": "point",
        "default_color": "#B0392C",
        "classify_fields": [
            ("name", "Town name"),
            ("fclass", "Settlement type"),
        ],
    },
    "major_towns": {
        "label": "Major Towns",
        "file": "major_towns.shp",
        "geometry": "point",
        "default_color": "#D98A2B",
        "classify_fields": [
            ("NAM", "Town name"),
            ("Province", "Province"),
        ],
    },
    "roads": {
        "label": "Roads",
        "file": "roads.shp",
        "geometry": "line",
        "default_color": "#4A4A4A",
        "classify_fields": [
            ("RTT_DESCRI", "Route type"),
            ("EXS_DESCRI", "Status"),
            ("ACC_DESCRI", "Accuracy"),
        ],
    },
    "rivers": {
        "label": "Rivers",
        "file": "rivers.shp",
        "geometry": "line",
        "default_color": "#2C6E8F",
        "classify_fields": [
            ("Name", "River name"),
            ("CATCHM_LE1", "Catchment level"),
        ],
    },
    "lakes": {
        "label": "Lakes",
        "file": "lakes.shp",
        "geometry": "polygon",
        "default_color": "#5FA8D3",
        "classify_fields": [
            ("Name", "Lake name"),
            ("CATCHM_LE1", "Catchment level"),
        ],
    },
    "mangroves": {
        "label": "Mangroves",
        "file": "mangroves.shp",
        "geometry": "polygon",
        "default_color": "#2F6B4F",
        "classify_fields": [
            ("Name", "Type"),
        ],
    },
    "forest_reserves": {
        "label": "Forest Reserves",
        "file": "forest_reserves.shp",
        "geometry": "polygon",
        "default_color": "#1F5C34",
        "classify_fields": [
            ("NAME", "Reserve name"),
            ("DISTRICT", "District"),
            ("Usage1", "Primary usage"),
        ],
    },
}

# Layer order matters for draw order: draw regions/districts under the
# more detailed layers, points on top.
LAYER_ORDER = [
    "regions",
    "districts",
    "chiefdoms",
    "sections",
    "forest_reserves",
    "mangroves",
    "lakes",
    "rivers",
    "roads",
    "towns",
    "major_towns",
]

# Friendlier aliases for a handful of otherwise-cryptic source field names.
# Applied to the layer so attribute tables / popups read better. Fields not
# listed here keep their original shapefile name.
FIELD_ALIASES = {
    "districts": {
        "DISTICT": "District",
    },
    "chiefdoms": {
        "FIRST_New_": "Chiefdom",
        "FIRST_FI_1": "District",
        "FIRST_FI_2": "Headquarter Town",
        "SUM_SUM_Fi": "Female Population",
        "SUM_SUM__1": "Total Population",
        "SUM_SUM_HO": "Households",
    },
    "sections": {
        "FIRST_SECT": "Section",
        "FIRST_New_": "Chiefdom",
        "FIRST_New1": "District",
        "FIRST_Ne_2": "Region",
        "SUM_Final_": "Male Population",
        "SUM_Final1": "Female Population",
        "SUM_Fina_1": "Total Population",
        "SUM_HOUSEH": "Households",
    },
    "towns": {
        "name": "Town Name",
        "fclass": "Settlement Type",
        "population": "Population",
    },
    "major_towns": {
        "NAM": "Town Name",
        "TXT": "Label Text",
    },
    "forest_reserves": {
        "NAME": "Reserve Name",
        "DISTRICT": "District",
        "Usage1": "Primary Usage",
        "Usage2": "Secondary Usage",
        "Year_Const": "Year Constituted",
    },
}


def _shp_path(filename):
    return os.path.join(DATA_DIR, filename)


def load_source_layer(key):
    """Load one of the embedded shapefiles as a QgsVectorLayer."""
    layer_def = LAYER_DEFS[key]
    if layer_def["file"] is None:
        raise ValueError(f"'{key}' has no source shapefile (it is derived).")
    path = _shp_path(layer_def["file"])
    layer = QgsVectorLayer(path, layer_def["label"], "ogr")
    if not layer.isValid():
        raise RuntimeError(f"Could not load embedded shapefile for '{key}': {path}")
    _apply_aliases(layer, key)
    return layer


def _apply_aliases(layer, key):
    aliases = FIELD_ALIASES.get(key, {})
    for field_name, alias in aliases.items():
        idx = layer.fields().indexFromName(field_name)
        if idx != -1:
            layer.setFieldAlias(idx, alias)


def _district_to_region_map(sections=None):
    if sections is None:
        sections = load_source_layer("sections")
    mapping = {}
    for feat in sections.getFeatures():
        district = feat["FIRST_New1"]
        region = feat["FIRST_Ne_2"]
        if district and region:
            mapping[str(district)] = str(region)
    return mapping


def build_region_geometries(districts=None, sections=None):
    """Return {region_name: unioned QgsGeometry} by dissolving Districts
    using the region/district relationship recorded in the Sections data.
    """
    if districts is None:
        districts = load_source_layer("districts")
    district_to_region = _district_to_region_map(sections)

    region_geoms = defaultdict(list)
    for feat in districts.getFeatures():
        district_name = str(feat["DISTICT"])
        region_name = district_to_region.get(district_name, "Unclassified")
        geom = feat.geometry()
        if geom is not None and not geom.isEmpty():
            region_geoms[region_name].append(QgsGeometry(geom))

    return {name: QgsGeometry.unaryUnion(geoms) for name, geoms in region_geoms.items()}


def build_regions_layer():
    """Derive a Regions polygon layer by dissolving Districts according to
    the region/district relationship already present in the Sections data.
    """
    districts = load_source_layer("districts")
    region_geoms = build_region_geometries(districts)

    mem_layer = QgsVectorLayer(
        f"Polygon?crs={districts.crs().authid()}", LAYER_DEFS["regions"]["label"], "memory"
    )
    provider = mem_layer.dataProvider()
    provider.addAttributes([QgsField("REGION", QVariant.String, len=100)])
    mem_layer.updateFields()

    features = []
    for region_name, geom in region_geoms.items():
        feat = QgsFeature(mem_layer.fields())
        feat.setGeometry(geom)
        feat.setAttribute("REGION", region_name)
        features.append(feat)

    provider.addFeatures(features)
    mem_layer.updateExtents()
    return mem_layer


def get_district_names():
    districts = load_source_layer("districts")
    return sorted({str(f["DISTICT"]) for f in districts.getFeatures() if f["DISTICT"]})


def get_region_names():
    return sorted(build_region_geometries().keys())


def get_boundary_geometry(boundary_type, value):
    """boundary_type: 'district' or 'region'. Returns a QgsGeometry, or
    None if not found."""
    if boundary_type == "district":
        districts = load_source_layer("districts")
        for feat in districts.getFeatures():
            if str(feat["DISTICT"]) == value:
                return QgsGeometry(feat.geometry())
        return None
    elif boundary_type == "region":
        region_geoms = build_region_geometries()
        return region_geoms.get(value)
    else:
        raise ValueError(f"Unknown boundary_type: {boundary_type}")


def _quote_sql_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def filter_sections_by_boundary(sections_layer, boundary_type, value):
    """Attribute-based filter: Sections already carry District/Region
    attributes, so no spatial test is needed."""
    field = "FIRST_New1" if boundary_type == "district" else "FIRST_Ne_2"
    sections_layer.setSubsetString(f"{field} = {_quote_sql_literal(value)}")


def filter_towns_by_boundary(towns_layer, boundary_geom):
    """Spatial filter: Towns have no district/region attribute, so find
    which town points fall inside the given boundary geometry."""
    if boundary_geom is None or boundary_geom.isEmpty():
        towns_layer.setSubsetString("FID = -1")
        return 0

    index = QgsSpatialIndex(towns_layer.getFeatures())
    candidate_ids = index.intersects(boundary_geom.boundingBox())

    matching_ids = []
    for fid in candidate_ids:
        feat = towns_layer.getFeature(fid)
        geom = feat.geometry()
        if geom is not None and boundary_geom.contains(geom):
            matching_ids.append(fid)

    if not matching_ids:
        towns_layer.setSubsetString("FID = -1")
        return 0

    id_list = ",".join(str(i) for i in matching_ids)
    towns_layer.setSubsetString(f"FID IN ({id_list})")
    return len(matching_ids)


def clear_boundary_filter(layer):
    layer.setSubsetString("")


def load_layer(key):
    """Load any layer in the catalogue, deriving Regions if needed."""
    if key == "regions":
        return build_regions_layer()
    return load_source_layer(key)


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

def _base_symbol(geometry_type_str):
    if geometry_type_str == "polygon":
        geom_type = QgsWkbTypes.PolygonGeometry
    elif geometry_type_str == "line":
        geom_type = QgsWkbTypes.LineGeometry
    else:
        geom_type = QgsWkbTypes.PointGeometry
    return QgsSymbol.defaultSymbol(geom_type)


def _style_symbol(symbol, geometry_type_str):
    """Apply sensible outline/width defaults on top of the fill/line color."""
    if geometry_type_str == "polygon":
        symbol.symbolLayer(0).setStrokeColor(QColor("#333333"))
        symbol.symbolLayer(0).setStrokeWidth(0.3)
    elif geometry_type_str == "line":
        symbol.symbolLayer(0).setWidth(0.6)


def apply_single_color(layer, key):
    layer_def = LAYER_DEFS[key]
    symbol = _base_symbol(layer_def["geometry"])
    color = QColor(layer_def["default_color"])
    symbol.setColor(color)
    _style_symbol(symbol, layer_def["geometry"])
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.triggerRepaint()


def available_ramp_names():
    """Color ramp names known to QGIS's default style, for the dropdown."""
    try:
        names = QgsStyle.defaultStyle().colorRampNames()
        return sorted(names)
    except Exception:
        return []


def _color_for_index(i, n, ramp):
    if ramp is not None and n > 0:
        pos = i / (n - 1) if n > 1 else 0.0
        return ramp.color(pos)
    # Fallback: deterministic pseudo-random color per index so repeated
    # renders of the same categories stay stable.
    rnd = random.Random(i * 7919 + 13)
    return QColor(rnd.randint(40, 220), rnd.randint(40, 220), rnd.randint(40, 220))


def apply_categorized_renderer(layer, key, field_name, ramp_name=None):
    layer_def = LAYER_DEFS[key]
    idx = layer.fields().indexFromName(field_name)
    if idx == -1:
        raise ValueError(f"Field '{field_name}' not found on layer '{key}'.")

    values = layer.uniqueValues(idx)
    unique_values = sorted(values, key=lambda v: (v is None, str(v)))

    style = QgsStyle.defaultStyle()
    ramp = None
    if ramp_name and ramp_name in style.colorRampNames():
        ramp = style.colorRamp(ramp_name)

    categories = []
    n = len(unique_values)
    for i, value in enumerate(unique_values):
        symbol = _base_symbol(layer_def["geometry"])
        color = _color_for_index(i, n, ramp)
        symbol.setColor(color)
        _style_symbol(symbol, layer_def["geometry"])
        label = str(value) if value not in (None, "") else "(blank)"
        categories.append(QgsRendererCategory(value, symbol, label))

    renderer = QgsCategorizedSymbolRenderer(field_name, categories)
    layer.setRenderer(renderer)
    layer.triggerRepaint()
