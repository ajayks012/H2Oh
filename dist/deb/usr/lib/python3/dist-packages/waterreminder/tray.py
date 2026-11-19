"""Minimal StatusNotifierItem + dbusmenu over Gio D-Bus. Silent no-op if no tray host exists."""
import logging
import os

from gi.repository import Gio, GLib

log = logging.getLogger("waterreminder")

SNI_XML = """<node><interface name="org.kde.StatusNotifierItem">
<method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
<signal name="NewStatus"><arg type="s"/></signal>
<property name="Category" type="s" access="read"/><property name="Id" type="s" access="read"/>
<property name="Title" type="s" access="read"/><property name="Status" type="s" access="read"/>
<property name="IconName" type="s" access="read"/><property name="IconThemePath" type="s" access="read"/>
<property name="Menu" type="o" access="read"/><property name="ItemIsMenu" type="b" access="read"/>
</interface></node>"""
MENU_XML = """<node><interface name="com.canonical.dbusmenu">
<method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/>
<arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/></method>
<method name="GetGroupProperties"><arg type="ai" direction="in"/><arg type="as" direction="in"/><arg type="a(ia{sv})" direction="out"/></method>
<method name="GetProperty"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method>
<method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/><arg type="u" direction="in"/></method>
<method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
<signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
<property name="Version" type="u" access="read"/><property name="TextDirection" type="s" access="read"/>
<property name="Status" type="s" access="read"/>
</interface></node>"""
WATCHER = ("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher", "org.kde.StatusNotifierWatcher")


class Tray:
    """`items()` returns [(id, label, enabled)]; `on_click(id)` handles activation."""

    def __init__(self, icon_dir, items, on_click):
        self.items, self.on_click, self.icon_dir, self.rev = items, on_click, icon_dir, 1
        self.con = None
        try:
            self.con = Gio.bus_get_sync(Gio.BusType.SESSION)
            self.name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
            self.con.register_object("/StatusNotifierItem", Gio.DBusNodeInfo.new_for_xml(SNI_XML).interfaces[0], self._sni_call, self._sni_get, None)
            self.con.register_object("/MenuBar", Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0], self._menu_call, self._menu_get, None)
            Gio.bus_own_name_on_connection(self.con, self.name, Gio.BusNameOwnerFlags.NONE, None, None)
            Gio.bus_watch_name_on_connection(self.con, WATCHER[0], Gio.BusNameWatcherFlags.NONE, self._register, None)
        except GLib.Error as e:
            log.warning("tray: unavailable (%s)", e.message)

    def _register(self, con, *_):
        con.call(WATCHER[0], WATCHER[1], WATCHER[2], "RegisterStatusNotifierItem", GLib.Variant("(s)", (self.name,)), None, Gio.DBusCallFlags.NONE, 2000, None, lambda *a: None)

    def refresh(self):
        self.rev += 1
        if self.con:
            self.con.emit_signal(None, "/MenuBar", "com.canonical.dbusmenu", "LayoutUpdated", GLib.Variant("(ui)", (self.rev, 0)))

    def _sni_get(self, con, sender, path, iface, prop):
        v = {"Category": "ApplicationStatus", "Id": "waterreminder", "Title": "H2Oh!", "Status": "Active",
             "IconName": "waterreminder", "IconThemePath": str(self.icon_dir)}
        if prop in v:
            return GLib.Variant("s", v[prop])
        return GLib.Variant("o", "/MenuBar") if prop == "Menu" else GLib.Variant("b", True)

    def _sni_call(self, con, sender, path, iface, method, params, inv):
        inv.return_value(None)

    def _menu_get(self, con, sender, path, iface, prop):
        return GLib.Variant("u", 3) if prop == "Version" else GLib.Variant("s", "ltr" if prop == "TextDirection" else "normal")

    def _props(self, label, enabled):
        return {"label": GLib.Variant("s", label), "enabled": GLib.Variant("b", enabled)}

    def _menu_call(self, con, sender, path, iface, method, params, inv):
        items = self.items()
        if method == "GetLayout":
            kids = [GLib.Variant("(ia{sv}av)", (i, self._props(l, e), [])) for i, l, e in items]
            root = (0, {"children-display": GLib.Variant("s", "submenu")}, kids)
            inv.return_value(GLib.Variant("(u(ia{sv}av))", (self.rev, root)))
        elif method == "GetGroupProperties":
            inv.return_value(GLib.Variant("(a(ia{sv}))", ([(i, self._props(l, e)) for i, l, e in items],)))
        elif method == "Event":
            ident, event = params.unpack()[:2]
            if event == "clicked":
                GLib.idle_add(self.on_click, ident)
            inv.return_value(None)
        elif method == "AboutToShow":
            inv.return_value(GLib.Variant("(b)", (False,)))
        else:
            inv.return_error_literal(Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD, method)
