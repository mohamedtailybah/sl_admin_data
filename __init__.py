def classFactory(iface):
    from .sl_admin_plugin import SLAdminBoundariesPlugin
    return SLAdminBoundariesPlugin(iface)
