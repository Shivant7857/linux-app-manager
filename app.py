#!/usr/bin/env python3
import sys
import os
import threading
import subprocess

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib, Gdk

from scanner import scan_all_applications

CSS_STYLES = b"""
.badge {
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
}
.badge-flatpak {
    background-color: rgba(46, 194, 126, 0.2);
    color: #2ec27e;
    border: 1px solid rgba(46, 194, 126, 0.5);
}
.badge-deb {
    background-color: rgba(53, 132, 228, 0.2);
    color: #3584e4;
    border: 1px solid rgba(53, 132, 228, 0.5);
}
.badge-snap {
    background-color: rgba(230, 97, 0, 0.2);
    color: #e66100;
    border: 1px solid rgba(230, 97, 0, 0.5);
}
.badge-appimage {
    background-color: rgba(145, 65, 172, 0.2);
    color: #c061cb;
    border: 1px solid rgba(145, 65, 172, 0.5);
}
.badge-size {
    background-color: rgba(127, 127, 127, 0.15);
    color: #9a9996;
    border-radius: 10px;
    padding: 2px 7px;
    font-size: 11px;
}
.app-card {
    padding: 10px 14px;
    margin: 4px 8px;
    border-radius: 10px;
    background-color: alpha(currentColor, 0.03);
    transition: background 200ms ease;
}
.app-card:hover {
    background-color: alpha(currentColor, 0.07);
}
.app-title {
    font-weight: 700;
    font-size: 14px;
}
.app-desc {
    color: #888;
    font-size: 12px;
}
"""

class AppRow(Gtk.Box):
    def __init__(self, app_data, on_open, on_delete):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        self.app_data = app_data
        self.add_css_class('app-card')
        
        # Icon
        icon_name = app_data.get('icon') or 'application-x-executable'
        self.icon_image = Gtk.Image.new_from_icon_name(icon_name)
        self.icon_image.set_pixel_size(44)
        self.append(self.icon_image)
        
        # Info Box (Title + Badges + Description)
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info_box.set_hexpand(True)
        info_box.set_valign(Gtk.Align.CENTER)
        
        # Header Line (Name + Badges)
        header_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        name_label = Gtk.Label(label=app_data.get('name', 'Unknown'))
        name_label.add_css_class('app-title')
        name_label.set_halign(Gtk.Align.START)
        name_label.set_ellipsize(3) # PANGO_ELLIPSIZE_END
        header_line.append(name_label)
        
        # Package Type Badge
        pkg_type = app_data.get('type', 'Other')
        type_badge = Gtk.Label(label=pkg_type)
        type_badge.add_css_class('badge')
        if 'Flatpak' in pkg_type:
            type_badge.add_css_class('badge-flatpak')
        elif 'Debian' in pkg_type:
            type_badge.add_css_class('badge-deb')
        elif 'Snap' in pkg_type:
            type_badge.add_css_class('badge-snap')
        elif 'AppImage' in pkg_type:
            type_badge.add_css_class('badge-appimage')
        header_line.append(type_badge)
        
        # Size Badge (if available)
        size_val = app_data.get('size', '').strip()
        if size_val:
            size_badge = Gtk.Label(label=size_val)
            size_badge.add_css_class('badge-size')
            header_line.append(size_badge)
            
        info_box.append(header_line)
        
        # Description / Details
        desc_text = app_data.get('description', '') or app_data.get('id', '')
        desc_label = Gtk.Label(label=desc_text)
        desc_label.add_css_class('app-desc')
        desc_label.set_halign(Gtk.Align.START)
        desc_label.set_ellipsize(3)
        desc_label.set_max_width_chars(60)
        info_box.append(desc_label)
        
        self.append(info_box)
        
        # Buttons Box (Open & Delete)
        buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons_box.set_valign(Gtk.Align.CENTER)
        
        # Open Button
        self.open_btn = Gtk.Button()
        open_content = Adw.ButtonContent(icon_name='media-playback-start-symbolic', label='Open')
        self.open_btn.set_child(open_content)
        self.open_btn.add_css_class('suggested-action')
        self.open_btn.connect('clicked', lambda _: on_open(self.app_data))
        buttons_box.append(self.open_btn)
        
        # Delete Button
        self.del_btn = Gtk.Button()
        del_content = Adw.ButtonContent(icon_name='user-trash-symbolic', label='Delete')
        self.del_btn.set_child(del_content)
        self.del_btn.add_css_class('destructive-action')
        
        if app_data.get('is_system', False):
            self.del_btn.set_sensitive(False)
            self.del_btn.set_tooltip_text("System Core App: Protected from deletion to keep OS safe.")
        else:
            self.del_btn.connect('clicked', lambda _: on_delete(self.app_data, self))
            
        buttons_box.append(self.del_btn)
        
        self.append(buttons_box)

class LinuxAppManagerWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_title("Linux App Manager")
        self.set_default_size(880, 640)
        
        self.apps = []
        self.active_filter = 'All'
        self.search_query = ''
        
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)
        
        # Main layout
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast_overlay.set_child(main_vbox)
        
        # Header Bar
        header = Adw.HeaderBar()
        title_widget = Adw.WindowTitle(title="Linux App Manager", subtitle="Manage .deb, Flatpak, Snap & AppImage")
        header.set_title_widget(title_widget)
        
        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Refresh Application List")
        refresh_btn.connect("clicked", lambda _: self.load_applications_async())
        header.pack_end(refresh_btn)
        
        main_vbox.append(header)
        
        # Controls Bar (Search + Filter pills)
        controls_bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        controls_bar.set_margin_top(12)
        controls_bar.set_margin_bottom(8)
        controls_bar.set_margin_start(16)
        controls_bar.set_margin_end(16)
        
        # Scrolled List
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.add_css_class('rich-list')
        scrolled.set_child(self.list_box)

        # Search Entry
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search installed apps by name or description...")
        self.search_entry.connect('search-changed', self.on_search_changed)
        controls_bar.append(self.search_entry)
        
        # Filter Buttons (Horizontal Box)
        filters_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        filters_box.set_halign(Gtk.Align.CENTER)
        
        self.filter_buttons = {}
        for ftype in ['All', 'Flatpak', 'Debian (.deb)', 'Snap', 'AppImage']:
            btn = Gtk.ToggleButton(label=ftype)
            btn.connect('toggled', self.on_filter_toggled, ftype)
            filters_box.append(btn)
            self.filter_buttons[ftype] = btn
            
        self.filter_buttons['All'].set_active(True)
        controls_bar.append(filters_box)
        main_vbox.append(controls_bar)
        
        self.status_label = Gtk.Label(label="Scanning applications...")
        self.status_label.add_css_class('dim-label')
        self.status_label.set_margin_bottom(4)
        main_vbox.append(self.status_label)
        main_vbox.append(scrolled)
        
        self._is_initialized = True
        
        # Initial scan
        self.load_applications_async()

    def show_toast(self, text, timeout=3):
        toast = Adw.Toast.new(text)
        toast.set_timeout(timeout)
        self.toast_overlay.add_toast(toast)

    def load_applications_async(self):
        self.status_label.set_text("Scanning applications...")
        def worker():
            apps = scan_all_applications()
            GLib.idle_add(self.on_apps_loaded, apps)
        threading.Thread(target=worker, daemon=True).start()

    def on_apps_loaded(self, apps):
        self.apps = apps
        self.update_counts()
        self.render_app_list()

    def update_counts(self):
        counts = {'All': len(self.apps), 'Flatpak': 0, 'Debian (.deb)': 0, 'Snap': 0, 'AppImage': 0}
        for a in self.apps:
            t = a.get('type')
            if t in counts:
                counts[t] += 1
        for k, btn in self.filter_buttons.items():
            btn.set_label(f"{k} ({counts.get(k, 0)})")

    def on_filter_toggled(self, button, filter_name):
        if not getattr(self, '_is_initialized', False):
            return
        if button.get_active():
            self.active_filter = filter_name
            for k, btn in self.filter_buttons.items():
                if k != filter_name and btn.get_active():
                    btn.set_active(False)
            self.render_app_list()
        else:
            # If all untoggled, keep 'All' active
            if not any(btn.get_active() for btn in self.filter_buttons.values()):
                self.filter_buttons['All'].set_active(True)

    def on_search_changed(self, entry):
        self.search_query = entry.get_text().strip().lower()
        self.render_app_list()

    def render_app_list(self):
        if not hasattr(self, 'list_box'):
            return
        # Clear existing
        while True:
            child = self.list_box.get_first_child()
            if not child:
                break
            self.list_box.remove(child)

        filtered = []
        for app in self.apps:
            if self.active_filter != 'All' and app.get('type') != self.active_filter:
                continue
            if self.search_query:
                name = app.get('name', '').lower()
                desc = app.get('description', '').lower()
                appid = app.get('id', '').lower()
                if self.search_query not in name and self.search_query not in desc and self.search_query not in appid:
                    continue
            filtered.append(app)

        self.status_label.set_text(f"Showing {len(filtered)} of {len(self.apps)} applications")

        for app in filtered:
            row = AppRow(app, self.handle_open, self.handle_delete)
            self.list_box.append(row)

    def handle_open(self, app):
        name = app.get('name', 'Application')
        self.show_toast(f"Launching {name}...")
        def run_app():
            try:
                if app.get('type') == 'AppImage':
                    subprocess.Popen([app['path']], start_new_session=True)
                elif app.get('id') and app.get('type') == 'Debian (.deb)':
                    subprocess.Popen(['gtk-launch', app['id']], start_new_session=True)
                else:
                    subprocess.Popen(app['exec_cmd'], shell=True, start_new_session=True)
            except Exception as e:
                GLib.idle_add(lambda: self.show_toast(f"Error launching: {e}"))
        threading.Thread(target=run_app, daemon=True).start()

    def handle_delete(self, app, row_widget):
        name = app.get('name', 'Application')
        pkg_type = app.get('type', '')
        uninstall_cmd = app.get('uninstall_cmd', '')

        # Confirmation Dialog
        dialog = Adw.MessageDialog.new(self, f"Uninstall {name}?", None)
        body = f"Are you sure you want to remove this {pkg_type} application?\n\nCommand: {uninstall_cmd}"
        if app.get('requires_root'):
            body += "\n\n(A system password prompt will appear to authorize uninstallation)"
        dialog.set_body(body)

        dialog.add_response("cancel", "Cancel")
        dialog.add_response("uninstall", "Uninstall")
        dialog.set_response_appearance("uninstall", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(dlg, response):
            if response == "uninstall":
                self.execute_uninstall(app, row_widget)

        dialog.connect("response", on_response)
        dialog.present()

    def execute_uninstall(self, app, row_widget):
        name = app.get('name', 'Application')
        self.show_toast(f"Uninstalling {name}... Please wait")
        row_widget.del_btn.set_sensitive(False)
        row_widget.open_btn.set_sensitive(False)

        def worker():
            cmd = app.get('uninstall_cmd')
            try:
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if res.returncode == 0:
                    GLib.idle_add(self.on_uninstall_success, app)
                else:
                    err_msg = res.stderr.strip() or "Process was cancelled or failed."
                    GLib.idle_add(self.on_uninstall_failed, name, err_msg, row_widget)
            except Exception as e:
                GLib.idle_add(self.on_uninstall_failed, name, str(e), row_widget)

        threading.Thread(target=worker, daemon=True).start()

    def on_uninstall_success(self, app):
        name = app.get('name', 'Application')
        self.show_toast(f"✓ {name} was successfully removed!", timeout=5)
        # Reload apps list
        self.load_applications_async()

    def on_uninstall_failed(self, name, error_msg, row_widget):
        row_widget.del_btn.set_sensitive(True)
        row_widget.open_btn.set_sensitive(True)
        
        # Check if user cancelled polkit prompt
        if "Authentication failed" in error_msg or "cancelled" in error_msg.lower() or "not authorized" in error_msg.lower():
            self.show_toast(f"Uninstallation cancelled by user.")
        else:
            dialog = Adw.MessageDialog.new(self, f"Uninstallation Failed", None)
            dialog.set_body(f"Failed to remove {name}:\n\n{error_msg[:300]}")
            dialog.add_response("ok", "OK")
            dialog.present()

class LinuxAppManager(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="com.github.linuxappmanager.App",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )

    def do_startup(self):
        Adw.Application.do_startup(self)
        display = Gdk.Display.get_default()
        if display:
            provider = Gtk.CssProvider()
            provider.load_from_data(CSS_STYLES)
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = LinuxAppManagerWindow(application=self)
        win.present()

if __name__ == '__main__':
    app = LinuxAppManager()
    sys.exit(app.run(sys.argv))
