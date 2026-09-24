import os

from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon

from .sl_admin_dialog import SLAdminBoundariesDialog


class SLAdminBoundariesPlugin:
    """Sierra Leone Administrative Boundaries - embedded shapefiles,
    boundary-type selection, and color classification."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = "&Sierra Leone Boundaries"
        self.toolbar = self.iface.addToolBar("Sierra Leone Boundaries")
        self.toolbar.setObjectName("SLAdminBoundariesToolbar")
        self.dlg = None

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        action = QAction(icon, "Sierra Leone Administrative Boundaries", self.iface.mainWindow())
        action.triggered.connect(self.run)
        action.setEnabled(True)

        self.toolbar.addAction(action)
        self.iface.addPluginToMenu(self.menu, action)
        self.actions.append(action)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar

    def run(self):
        if self.dlg is None:
            self.dlg = SLAdminBoundariesDialog(self.iface.mainWindow())
        self.dlg.show()
        self.dlg.exec_()
