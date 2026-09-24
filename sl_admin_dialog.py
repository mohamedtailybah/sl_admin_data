from qgis.core import QgsProject
from qgis.utils import iface
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QCheckBox,
    QComboBox,
    QLabel,
    QPushButton,
    QGroupBox,
    QMessageBox,
    QDialogButtonBox,
    QScrollArea,
)
from qgis.PyQt.QtCore import Qt

from . import boundary_data
from .boundary_data import LAYER_DEFS, LAYER_ORDER


NONE_FIELD = "-- single color (no classification) --"


class SLAdminBoundariesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sierra Leone Administrative Boundaries")
        self.setMinimumWidth(560)
        self.resize(560, 720)

        # key -> QgsMapLayer currently added to the project by this dialog
        self.active_layers = {key: None for key in LAYER_ORDER}

        self.checkboxes = {}
        self.field_combos = {}

        main_layout = QVBoxLayout()

        intro = QLabel(
            "All boundary data is embedded in this plugin - no shapefiles needed.\n"
            "Choose which boundary types to display, and optionally color each\n"
            "layer by one of its attributes."
        )
        intro.setWordWrap(True)
        main_layout.addWidget(intro)

        grid_box = QGroupBox("Boundary layers")
        grid = QGridLayout()
        grid.addWidget(QLabel("<b>Show</b>"), 0, 0)
        grid.addWidget(QLabel("<b>Layer</b>"), 0, 1)
        grid.addWidget(QLabel("<b>Classify by</b>"), 0, 2)

        for row, key in enumerate(LAYER_ORDER, start=1):
            layer_def = LAYER_DEFS[key]

            checkbox = QCheckBox()
            checkbox.setChecked(key in ("districts", "towns"))
            self.checkboxes[key] = checkbox
            grid.addWidget(checkbox, row, 0, alignment=Qt.AlignCenter)

            label = QLabel(layer_def["label"])
            grid.addWidget(label, row, 1)

            combo = QComboBox()
            combo.addItem(NONE_FIELD, None)
            for field_name, field_label in layer_def["classify_fields"]:
                combo.addItem(field_label, field_name)
            if layer_def["classify_fields"]:
                combo.setCurrentIndex(1)  # default to first real field
            self.field_combos[key] = combo
            grid.addWidget(combo, row, 2)

        grid_box.setLayout(grid)

        grid_scroll = QScrollArea()
        grid_scroll.setWidgetResizable(True)
        grid_scroll.setWidget(grid_box)
        grid_scroll.setMinimumHeight(280)
        main_layout.addWidget(grid_scroll)

        select_row = QHBoxLayout()
        select_all_btn = QPushButton("Select all")
        select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        clear_all_btn = QPushButton("Clear all")
        clear_all_btn.clicked.connect(lambda: self._set_all_checked(False))
        select_row.addWidget(select_all_btn)
        select_row.addWidget(clear_all_btn)
        select_row.addStretch()
        main_layout.addLayout(select_row)

        ramp_box = QGroupBox("Color ramp for classification")
        ramp_layout = QHBoxLayout()
        ramp_layout.addWidget(QLabel("Ramp:"))
        self.ramp_combo = QComboBox()
        self.ramp_combo.addItem("Auto (distinct colors)", None)
        for name in boundary_data.available_ramp_names():
            self.ramp_combo.addItem(name, name)
        ramp_layout.addWidget(self.ramp_combo, 1)
        ramp_box.setLayout(ramp_layout)
        main_layout.addWidget(ramp_box)

        button_box = QDialogButtonBox()
        self.apply_btn = button_box.addButton("Apply", QDialogButtonBox.ApplyRole)
        self.apply_btn.clicked.connect(self.apply_selection)
        close_btn = button_box.addButton(QDialogButtonBox.Close)
        close_btn.clicked.connect(self.close)
        main_layout.addWidget(button_box)

        main_layout.addWidget(self._build_filter_box())

        self.setLayout(main_layout)

    # ------------------------------------------------------------------
    # Boundary filter (Towns & Sections, by Region or District)
    # ------------------------------------------------------------------
    def _build_filter_box(self):
        box = QGroupBox("Show only Towns && Sections within a Region or District")
        layout = QVBoxLayout()

        note = QLabel(
            "Sections are filtered by their recorded District/Region. Towns have no\n"
            "such attribute in the source data, so they're filtered spatially -\n"
            "only towns that fall inside the chosen boundary are shown."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        row = QHBoxLayout()
        row.addWidget(QLabel("Boundary type:"))
        self.boundary_type_combo = QComboBox()
        self.boundary_type_combo.addItem("District", "district")
        self.boundary_type_combo.addItem("Region", "region")
        self.boundary_type_combo.currentIndexChanged.connect(self._repopulate_boundary_values)
        row.addWidget(self.boundary_type_combo)

        row.addWidget(QLabel("Value:"))
        self.boundary_value_combo = QComboBox()
        row.addWidget(self.boundary_value_combo, 1)
        layout.addLayout(row)

        btn_row = QHBoxLayout()
        self.apply_filter_btn = QPushButton("Apply filter")
        self.apply_filter_btn.clicked.connect(self.apply_boundary_filter)
        self.clear_filter_btn = QPushButton("Clear filter")
        self.clear_filter_btn.clicked.connect(self.clear_boundary_filter)
        btn_row.addWidget(self.apply_filter_btn)
        btn_row.addWidget(self.clear_filter_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.filter_status_label = QLabel("")
        self.filter_status_label.setWordWrap(True)
        layout.addWidget(self.filter_status_label)

        box.setLayout(layout)
        self._repopulate_boundary_values()
        return box

    def _repopulate_boundary_values(self):
        boundary_type = self.boundary_type_combo.currentData()
        self.boundary_value_combo.clear()
        try:
            if boundary_type == "district":
                values = boundary_data.get_district_names()
            else:
                values = boundary_data.get_region_names()
        except Exception as e:
            QMessageBox.warning(self, "Could not load boundary names", str(e))
            values = []
        self.boundary_value_combo.addItems(values)

    def apply_boundary_filter(self):
        boundary_type = self.boundary_type_combo.currentData()
        value = self.boundary_value_combo.currentText()
        if not value:
            return

        try:
            # Make sure Sections and Towns are on the map before filtering.
            self.checkboxes["sections"].setChecked(True)
            self.checkboxes["towns"].setChecked(True)
            sections_layer = self._ensure_layer_shown("sections")
            towns_layer = self._ensure_layer_shown("towns")

            boundary_data.filter_sections_by_boundary(sections_layer, boundary_type, value)

            boundary_geom = boundary_data.get_boundary_geometry(boundary_type, value)
            town_count = boundary_data.filter_towns_by_boundary(towns_layer, boundary_geom)
            section_count = sections_layer.featureCount()

            self.filter_status_label.setText(
                f"Showing {section_count} section(s) and {town_count} town(s) "
                f"within {self.boundary_type_combo.currentText()} '{value}'."
            )

            if boundary_geom is not None and not boundary_geom.isEmpty() and iface is not None:
                iface.mapCanvas().setExtent(boundary_geom.boundingBox())
                iface.mapCanvas().refresh()
        except Exception as e:
            QMessageBox.warning(self, "Filter failed", str(e))

    def clear_boundary_filter(self):
        for key in ("sections", "towns"):
            layer = self._resolve_existing(key)
            if layer is not None:
                boundary_data.clear_boundary_filter(layer)
        self.filter_status_label.setText("Filter cleared - showing all sections and towns.")

    # ------------------------------------------------------------------
    # Layer show/hide + classification
    # ------------------------------------------------------------------
    def _set_all_checked(self, checked):
        for cb in self.checkboxes.values():
            cb.setChecked(checked)

    def _ensure_layer_shown(self, key):
        """Load+add the layer if needed, and return it."""
        existing = self._resolve_existing(key)
        if existing is not None:
            return existing
        layer = boundary_data.load_layer(key)
        QgsProject.instance().addMapLayer(layer)
        self.active_layers[key] = layer
        field_name = self.field_combos[key].currentData()
        if field_name:
            boundary_data.apply_categorized_renderer(layer, key, field_name, self.ramp_combo.currentData())
        else:
            boundary_data.apply_single_color(layer, key)
        return layer

    def apply_selection(self):
        errors = []
        ramp_name = self.ramp_combo.currentData()

        for key in LAYER_ORDER:
            wanted = self.checkboxes[key].isChecked()
            existing = self._resolve_existing(key)

            if not wanted:
                if existing is not None:
                    QgsProject.instance().removeMapLayer(existing.id())
                    self.active_layers[key] = None
                continue

            try:
                if existing is None:
                    layer = boundary_data.load_layer(key)
                    QgsProject.instance().addMapLayer(layer)
                    self.active_layers[key] = layer
                else:
                    layer = existing

                field_name = self.field_combos[key].currentData()
                if field_name:
                    boundary_data.apply_categorized_renderer(layer, key, field_name, ramp_name)
                else:
                    boundary_data.apply_single_color(layer, key)
            except Exception as e:
                errors.append(f"{LAYER_DEFS[key]['label']}: {e}")

        if errors:
            QMessageBox.warning(self, "Some layers had problems", "\n".join(errors))

    def _resolve_existing(self, key):
        """Return the tracked layer for `key` if it's still in the project."""
        layer = self.active_layers.get(key)
        if layer is None:
            return None
        if QgsProject.instance().mapLayer(layer.id()) is None:
            self.active_layers[key] = None
            return None
        return layer
