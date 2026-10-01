#!/usr/bin/env python3
import sys
import os
import threading
import subprocess
from datetime import datetime

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib, Gdk

import installer
import backup_manager
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
.badge-clone-data {
    background-color: rgba(46, 194, 126, 0.2);
    color: #2ec27e;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
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
.mode-card {
    padding: 14px 16px;
    border-radius: 12px;
    background-color: alpha(currentColor, 0.04);
    border: 2px solid transparent;
    transition: all 200ms ease;
}
.mode-card:hover {
    background-color: alpha(currentColor, 0.08);
}
.mode-card-active {
    background-color: rgba(53, 132, 228, 0.12);
    border-color: #3584e4;
}
.selection-toolbar {
    padding: 8px 12px;
    background-color: alpha(currentColor, 0.03);
    border-radius: 10px;
}
.log-view {
    background-color: rgba(0, 0, 0, 0.2);
    font-family: monospace;
    font-size: 12px;
    padding: 10px;
    border-radius: 8px;
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
        name_label.set_ellipsize(3)
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

class BackupAppRow(Gtk.Box):
    def __init__(self, app_data, is_selected, on_toggle):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.app_data = app_data
        self.on_toggle = on_toggle
        self.add_css_class('app-card')
        
        # Checkbox
        self.check = Gtk.CheckButton()
        self.check.set_active(is_selected)
        self.check.set_valign(Gtk.Align.CENTER)
        self.check.connect('toggled', self._on_checked)
        self.append(self.check)
        
        # Icon
        icon_name = app_data.get('icon') or 'application-x-executable'
        icon_img = Gtk.Image.new_from_icon_name(icon_name)
        icon_img.set_pixel_size(36)
        icon_img.set_valign(Gtk.Align.CENTER)
        self.append(icon_img)
        
        # Details Box
        details_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        details_box.set_hexpand(True)
        details_box.set_valign(Gtk.Align.CENTER)
        
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name_label = Gtk.Label(label=app_data.get('name', 'Unknown'))
        name_label.add_css_class('app-title')
        name_label.set_halign(Gtk.Align.START)
        name_label.set_ellipsize(3)
        title_box.append(name_label)
        
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
        title_box.append(type_badge)
        
        details_box.append(title_box)
        
        desc_text = app_data.get('description', '') or app_data.get('id', '')
        desc_label = Gtk.Label(label=desc_text)
        desc_label.add_css_class('app-desc')
        desc_label.set_halign(Gtk.Align.START)
        desc_label.set_ellipsize(3)
        desc_label.set_max_width_chars(50)
        details_box.append(desc_label)
        self.append(details_box)
        
        # Data size badge (shown in clone mode)
        self.data_badge = Gtk.Label(label="Calculating...")
        self.data_badge.add_css_class('badge-clone-data')
        self.data_badge.set_valign(Gtk.Align.CENTER)
        self.data_badge.set_visible(False)
        self.append(self.data_badge)
        
        # Click on row to toggle check
        gesture = Gtk.GestureClick.new()
        gesture.connect('released', self._on_row_clicked)
        self.add_controller(gesture)

    def _on_row_clicked(self, gesture, n_press, x, y):
        # Toggle checkbox when clicking row
        self.check.set_active(not self.check.get_active())

    def _on_checked(self, btn):
        self.on_toggle(self.app_data, btn.get_active())

    def set_data_summary(self, summary_text):
        self.data_badge.set_label(summary_text)

class BackupCloneDialog(Adw.Window):
    def __init__(self, parent_window, apps_list):
        super().__init__()
        self.set_transient_for(parent_window)
        self.set_modal(True)
        self.set_title("Backup & Clone Applications")
        self.set_default_size(780, 680)
        self.parent_window = parent_window
        self.all_apps = list(apps_list)
        self.mode = "backup" # "backup" or "clone"
        
        # Track selected app IDs
        self.selected_ids = set(self._get_app_key(a) for a in self.all_apps)
        self.row_widgets = {}
        self.data_sizes = {}
        self.search_term = ""
        
        # Root layout
        root_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root_vbox)
        
        # HeaderBar
        header = Adw.HeaderBar()
        title_widget = Adw.WindowTitle(
            title="Backup & Clone",
            subtitle="Export applications or clone complete environments"
        )
        header.set_title_widget(title_widget)
        
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect('clicked', lambda _: self.close())
        header.pack_start(cancel_btn)
        root_vbox.append(header)
        
        # Main content stack (Normal View vs Progress View)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        root_vbox.append(self.stack)
        
        # PAGE 1: Configuration & Selection
        config_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        config_vbox.set_margin_top(14)
        config_vbox.set_margin_bottom(14)
        config_vbox.set_margin_start(16)
        config_vbox.set_margin_end(16)
        self.stack.add_named(config_vbox, "config")
        
        # Mode Chooser Cards
        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        mode_box.set_homogeneous(True)
        
        # Card 1: Backup (Apps Only)
        self.backup_card = Gtk.Button()
        self.backup_card.add_css_class('mode-card')
        self.backup_card.add_css_class('mode-card-active')
        b_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        b_title = Gtk.Label(label="📦 Backup (Apps Only)")
        b_title.add_css_class('app-title')
        b_desc = Gtk.Label(label="Lightweight blueprint + AppImages.\nFast multi-app deployment, no personal data.")
        b_desc.add_css_class('dim-label')
        b_desc.set_wrap(True)
        b_desc.set_justify(Gtk.Justification.CENTER)
        b_content.append(b_title)
        b_content.append(b_desc)
        self.backup_card.set_child(b_content)
        self.backup_card.connect('clicked', lambda _: self.set_mode('backup'))
        mode_box.append(self.backup_card)
        
        # Card 2: Clone (Apps + Data)
        self.clone_card = Gtk.Button()
        self.clone_card.add_css_class('mode-card')
        c_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        c_title = Gtk.Label(label="🧬 Clone (Apps + Login Data)")
        c_title.add_css_class('app-title')
        c_desc = Gtk.Label(label="Exact working state replica.\nPreserves logins, sessions, tokens & databases.")
        c_desc.add_css_class('dim-label')
        c_desc.set_wrap(True)
        c_desc.set_justify(Gtk.Justification.CENTER)
        c_content.append(c_title)
        c_content.append(c_desc)
        self.clone_card.set_child(c_content)
        self.clone_card.connect('clicked', lambda _: self.set_mode('clone'))
        mode_box.append(self.clone_card)
        
        config_vbox.append(mode_box)
        
        # Selection & Search Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        toolbar.add_css_class('selection-toolbar')
        
        self.select_all_btn = Gtk.Button(label="Deselect All")
        self.select_all_btn.connect('clicked', self.on_toggle_all)
        toolbar.append(self.select_all_btn)
        
        self.counter_label = Gtk.Label()
        self.counter_label.set_hexpand(True)
        self.counter_label.set_halign(Gtk.Align.START)
        toolbar.append(self.counter_label)
        
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Filter apps...")
        self.search_entry.set_size_request(220, -1)
        self.search_entry.connect('search-changed', self.on_search_changed)
        toolbar.append(self.search_entry)
        
        config_vbox.append(toolbar)
        
        # Scrolled App List
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.add_css_class('rich-list')
        scrolled.set_child(self.list_box)
        config_vbox.append(scrolled)
        
        # Bottom Action Bar
        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        action_bar.set_margin_top(8)
        
        self.info_summary_label = Gtk.Label()
        self.info_summary_label.add_css_class('dim-label')
        self.info_summary_label.set_hexpand(True)
        self.info_summary_label.set_halign(Gtk.Align.START)
        action_bar.append(self.info_summary_label)
        
        self.export_btn = Gtk.Button()
        self.export_btn_content = Adw.ButtonContent(
            icon_name="document-save-symbolic",
            label="Export Backup (.lam)"
        )
        self.export_btn.set_child(self.export_btn_content)
        self.export_btn.add_css_class("suggested-action")
        self.export_btn.connect('clicked', self.on_export_clicked)
        action_bar.append(self.export_btn)
        
        config_vbox.append(action_bar)
        
        # PAGE 2: Export Progress View
        progress_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        progress_vbox.set_valign(Gtk.Align.CENTER)
        progress_vbox.set_halign(Gtk.Align.CENTER)
        progress_vbox.set_margin_top(40)
        progress_vbox.set_margin_bottom(40)
        
        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(48, 48)
        progress_vbox.append(self.spinner)
        
        self.progress_title = Gtk.Label(label="Creating Package...")
        self.progress_title.add_css_class('title-2')
        progress_vbox.append(self.progress_title)
        
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_size_request(440, -1)
        self.progress_bar.set_show_text(True)
        progress_vbox.append(self.progress_bar)
        
        self.progress_status = Gtk.Label(label="Preparing applications...")
        self.progress_status.add_css_class('dim-label')
        progress_vbox.append(self.progress_status)
        
        self.stack.add_named(progress_vbox, "progress")
        
        # Render initial list
        self.render_apps()
        self.update_selection_counter()

    def _get_app_key(self, app):
        return app.get('id') or app.get('name')

    def set_mode(self, new_mode):
        self.mode = new_mode
        if new_mode == 'backup':
            self.backup_card.add_css_class('mode-card-active')
            self.clone_card.remove_css_class('mode-card-active')
            self.export_btn_content.set_label("Export Backup (.lam)")
        else:
            self.clone_card.add_css_class('mode-card-active')
            self.backup_card.remove_css_class('mode-card-active')
            self.export_btn_content.set_label("Export Clone (.lam)")
            self.calculate_clone_sizes_async()

        # Update visibility of data badges
        is_clone = (new_mode == 'clone')
        for key, row in self.row_widgets.items():
            row.data_badge.set_visible(is_clone)
        self.update_selection_counter()

    def calculate_clone_sizes_async(self):
        def worker():
            for app in self.all_apps:
                key = self._get_app_key(app)
                if key not in self.data_sizes:
                    sz_bytes, sz_str = backup_manager.get_app_data_summary(app)
                    self.data_sizes[key] = (sz_bytes, sz_str)
                    GLib.idle_add(self._update_row_data_size, key, sz_str)
            GLib.idle_add(self.update_selection_counter)
        threading.Thread(target=worker, daemon=True).start()

    def _update_row_data_size(self, key, sz_str):
        if key in self.row_widgets:
            self.row_widgets[key].set_data_summary(f"Data: {sz_str}")

    def on_toggle_app(self, app, is_checked):
        key = self._get_app_key(app)
        if is_checked:
            self.selected_ids.add(key)
        else:
            self.selected_ids.discard(key)
        self.update_selection_counter()

    def on_toggle_all(self, btn):
        if len(self.selected_ids) == len(self.all_apps):
            # Deselect all
            self.selected_ids.clear()
            self.select_all_btn.set_label("Select All")
        else:
            # Select all
            self.selected_ids = set(self._get_app_key(a) for a in self.all_apps)
            self.select_all_btn.set_label("Deselect All")
            
        for key, row in self.row_widgets.items():
            row.check.set_active(key in self.selected_ids)
        self.update_selection_counter()

    def on_search_changed(self, entry):
        self.search_term = entry.get_text().strip().lower()
        self.render_apps()

    def render_apps(self):
        while True:
            child = self.list_box.get_first_child()
            if not child:
                break
            self.list_box.remove(child)
            
        self.row_widgets.clear()
        
        for app in self.all_apps:
            name = app.get('name', '').lower()
            desc = app.get('description', '').lower()
            key = self._get_app_key(app)
            
            if self.search_term and (self.search_term not in name and self.search_term not in desc):
                continue
                
            is_selected = key in self.selected_ids
            row = BackupAppRow(app, is_selected, self.on_toggle_app)
            row.data_badge.set_visible(self.mode == 'clone')
            if key in self.data_sizes:
                row.set_data_summary(f"Data: {self.data_sizes[key][1]}")
                
            self.row_widgets[key] = row
            self.list_box.append(row)

    def update_selection_counter(self):
        sel_count = len(self.selected_ids)
        total_count = len(self.all_apps)
        self.counter_label.set_text(f"Selected: {sel_count} of {total_count} apps")
        
        if sel_count == total_count:
            self.select_all_btn.set_label("Deselect All")
        else:
            self.select_all_btn.set_label("Select All")
            
        self.export_btn.set_sensitive(sel_count > 0)
        
        if self.mode == 'clone':
            total_bytes = sum(self.data_sizes.get(k, (0, ''))[0] for k in self.selected_ids)
            self.info_summary_label.set_text(f"Estimated Cloned Data: ~{backup_manager.format_size(total_bytes)}")
        else:
            self.info_summary_label.set_text("Lightweight installation manifest & AppImages")

    def on_export_clicked(self, _):
        if not self.selected_ids:
            return
            
        selected_apps = [a for a in self.all_apps if self._get_app_key(a) in self.selected_ids]
        date_str = datetime.now().strftime("%Y-%m-%d")
        default_filename = f"linux-apps-{self.mode}-{date_str}.lam"
        
        downloads = os.path.expanduser('~/Downloads')
        home = os.path.expanduser('~')
        start_dir = downloads if os.path.isdir(downloads) else home
        initial_folder = Gio.File.new_for_path(start_dir)

        if hasattr(Gtk, 'FileDialog'):
            dialog = Gtk.FileDialog.new()
            dialog.set_title(f"Export {self.mode.capitalize()} Archive")
            dialog.set_initial_name(default_filename)
            dialog.set_initial_folder(initial_folder)

            filter_lam = Gtk.FileFilter()
            filter_lam.set_name("Linux App Manager Backup (*.lam)")
            filter_lam.add_pattern("*.lam")

            filters_list = Gio.ListStore.new(Gtk.FileFilter)
            filters_list.append(filter_lam)
            dialog.set_filters(filters_list)

            def on_save_finish(dlg, result):
                try:
                    gfile = dlg.save_finish(result)
                    if gfile:
                        path = gfile.get_path()
                        if path:
                            if not path.endswith('.lam'):
                                path += '.lam'
                            self.execute_export(selected_apps, path)
                except Exception:
                    pass

            dialog.save(self, None, on_save_finish)
        else:
            chooser = Gtk.FileChooserNative.new(
                f"Export {self.mode.capitalize()} Archive",
                self,
                Gtk.FileChooserAction.SAVE,
                "Export",
                "Cancel"
            )
            chooser.set_current_name(default_filename)
            chooser.set_current_folder(initial_folder)
            filter_lam = Gtk.FileFilter()
            filter_lam.set_name("Linux App Manager Backup (*.lam)")
            filter_lam.add_pattern("*.lam")
            chooser.add_filter(filter_lam)

            def on_response(dlg, response_id):
                if response_id == Gtk.ResponseType.ACCEPT:
                    gfile = dlg.get_file()
                    if gfile:
                        path = gfile.get_path()
                        if path:
                            if not path.endswith('.lam'):
                                path += '.lam'
                            self.execute_export(selected_apps, path)
                dlg.destroy()

            chooser.connect("response", on_response)
            chooser.show()

    def execute_export(self, selected_apps, target_path):
        self.stack.set_visible_child_name("progress")
        self.spinner.start()
        self.progress_title.set_text(f"Creating {self.mode.capitalize()} Package...")
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text("0%")
        
        def progress_cb(step, total, msg):
            def update():
                frac = min(1.0, max(0.0, step / max(1, total)))
                self.progress_bar.set_fraction(frac)
                self.progress_bar.set_text(f"{int(frac * 100)}%")
                self.progress_status.set_text(msg)
            GLib.idle_add(update)

        def worker():
            success, msg = backup_manager.create_backup_archive(
                selected_apps, self.mode, target_path, progress_callback=progress_cb
            )
            GLib.idle_add(self.on_export_finished, success, msg, target_path)

        threading.Thread(target=worker, daemon=True).start()

    def on_export_finished(self, success, msg, target_path):
        self.spinner.stop()
        if success:
            sz_str = backup_manager.format_size(os.path.getsize(target_path)) if os.path.exists(target_path) else ""
            dialog = Adw.MessageDialog.new(self, "Backup Complete! 🎉", None)
            body = f"Successfully exported package to:\n<b>{target_path}</b>"
            if sz_str:
                body += f"\n\n<b>Size:</b> {sz_str}"
            dialog.set_body(body)
            dialog.set_body_use_markup(True)
            dialog.add_response("ok", "OK")
            dialog.connect("response", lambda *_: self.close())
            dialog.present()
            self.parent_window.show_toast(f"✓ Backup exported successfully!")
        else:
            dialog = Adw.MessageDialog.new(self, "Export Failed", None)
            dialog.set_body(f"Failed to create archive:\n\n{msg}")
            dialog.add_response("ok", "OK")
            dialog.connect("response", lambda *_: self.stack.set_visible_child_name("config"))
            dialog.present()

class RestoreAppRow(Gtk.Box):
    def __init__(self, app_data, is_selected, on_toggle):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.app_data = app_data
        self.on_toggle = on_toggle
        self.add_css_class('app-card')
        
        self.check = Gtk.CheckButton()
        self.check.set_active(is_selected)
        self.check.set_valign(Gtk.Align.CENTER)
        self.check.connect('toggled', lambda btn: on_toggle(app_data, btn.get_active()))
        self.append(self.check)
        
        icon_img = Gtk.Image.new_from_icon_name('application-x-executable')
        icon_img.set_pixel_size(36)
        icon_img.set_valign(Gtk.Align.CENTER)
        self.append(icon_img)
        
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info_box.set_hexpand(True)
        info_box.set_valign(Gtk.Align.CENTER)
        
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name_label = Gtk.Label(label=app_data.get('name', 'Unknown'))
        name_label.add_css_class('app-title')
        title_box.append(name_label)
        
        pkg_type = app_data.get('type', '')
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
        title_box.append(type_badge)
        info_box.append(title_box)
        
        desc = app_data.get('description', '') or app_data.get('id', '')
        desc_label = Gtk.Label(label=desc)
        desc_label.add_css_class('app-desc')
        desc_label.set_halign(Gtk.Align.START)
        desc_label.set_ellipsize(3)
        info_box.append(desc_label)
        self.append(info_box)
        
        # Row click toggle
        gesture = Gtk.GestureClick.new()
        gesture.connect('released', lambda *_: self.check.set_active(not self.check.get_active()))
        self.add_controller(gesture)

class RestoreDialog(Adw.Window):
    def __init__(self, parent_window, archive_path):
        super().__init__()
        self.set_transient_for(parent_window)
        self.set_modal(True)
        self.set_title("Restore Applications")
        self.set_default_size(740, 640)
        self.parent_window = parent_window
        self.archive_path = archive_path
        
        # Inspect manifest
        try:
            self.manifest = backup_manager.inspect_backup_archive(archive_path)
        except Exception as e:
            dialog = Adw.MessageDialog.new(parent_window, "Invalid Backup File", None)
            dialog.set_body(f"Could not read backup archive:\n\n{str(e)}")
            dialog.add_response("ok", "OK")
            dialog.present()
            self.close()
            return
            
        self.apps = self.manifest.get('apps', [])
        self.selected_ids = set(a.get('id') or a.get('name') for a in self.apps)
        self.row_widgets = {}
        
        # Root layout
        root_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root_vbox)
        
        # HeaderBar
        header = Adw.HeaderBar()
        title_widget = Adw.WindowTitle(
            title="Restore Applications",
            subtitle=os.path.basename(archive_path)
        )
        header.set_title_widget(title_widget)
        
        self.close_btn = Gtk.Button(label="Cancel")
        self.close_btn.connect('clicked', lambda _: self.close())
        header.pack_start(self.close_btn)
        root_vbox.append(header)
        
        # Stack (Config vs Progress)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        root_vbox.append(self.stack)
        
        # PAGE 1: Inspection & Selection
        config_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        config_vbox.set_margin_top(14)
        config_vbox.set_margin_bottom(14)
        config_vbox.set_margin_start(16)
        config_vbox.set_margin_end(16)
        self.stack.add_named(config_vbox, "config")
        
        # Summary Card
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        card.add_css_class('mode-card')
        
        mode = self.manifest.get('mode', 'backup')
        mode_icon = Gtk.Label(label="🧬" if mode == 'clone' else "📦")
        mode_icon.set_markup(f"<span font='32'>{'🧬' if mode == 'clone' else '📦'}</span>")
        card.append(mode_icon)
        
        card_text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card_text_box.set_hexpand(True)
        mode_title = f"{'Clone (Apps + Login Data)' if mode == 'clone' else 'Backup (Applications Only)'}"
        m_label = Gtk.Label(label=f"<b>Type:</b> {mode_title}")
        m_label.set_use_markup(True)
        m_label.set_halign(Gtk.Align.START)
        card_text_box.append(m_label)
        
        created = self.manifest.get('created_at', '')
        if created:
            try:
                dt = datetime.fromisoformat(created)
                created = dt.strftime("%b %d, %Y at %I:%M %p")
            except Exception:
                pass
        d_label = Gtk.Label(label=f"<b>Created:</b> {created}   •   <b>Archive Size:</b> {self.manifest.get('archive_size', 'N/A')}")
        d_label.set_use_markup(True)
        d_label.set_halign(Gtk.Align.START)
        d_label.add_css_class('dim-label')
        card_text_box.append(d_label)
        
        card.append(card_text_box)
        config_vbox.append(card)
        
        # Selection Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        toolbar.add_css_class('selection-toolbar')
        
        self.select_all_btn = Gtk.Button(label="Deselect All")
        self.select_all_btn.connect('clicked', self.on_toggle_all)
        toolbar.append(self.select_all_btn)
        
        self.counter_label = Gtk.Label(label=f"Selected: {len(self.selected_ids)} of {len(self.apps)} apps to restore")
        self.counter_label.set_hexpand(True)
        self.counter_label.set_halign(Gtk.Align.START)
        toolbar.append(self.counter_label)
        config_vbox.append(toolbar)
        
        # Scrolled List
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.add_css_class('rich-list')
        scrolled.set_child(self.list_box)
        config_vbox.append(scrolled)
        
        for app in self.apps:
            key = app.get('id') or app.get('name')
            row = RestoreAppRow(app, True, self.on_toggle_app)
            self.row_widgets[key] = row
            self.list_box.append(row)
            
        # Action Bar
        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        action_bar.set_margin_top(8)
        
        info_lbl = Gtk.Label(label="Select the apps you want to install/restore on this system.")
        info_lbl.add_css_class('dim-label')
        info_lbl.set_hexpand(True)
        info_lbl.set_halign(Gtk.Align.START)
        action_bar.append(info_lbl)
        
        self.start_restore_btn = Gtk.Button()
        btn_content = Adw.ButtonContent(icon_name="folder-download-symbolic", label="Restore Selected Apps")
        self.start_restore_btn.set_child(btn_content)
        self.start_restore_btn.add_css_class("suggested-action")
        self.start_restore_btn.connect('clicked', self.on_start_restore)
        action_bar.append(self.start_restore_btn)
        
        config_vbox.append(action_bar)
        
        # PAGE 2: Progress & Logs View
        progress_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        progress_vbox.set_margin_top(20)
        progress_vbox.set_margin_bottom(20)
        progress_vbox.set_margin_start(20)
        progress_vbox.set_margin_end(20)
        
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        progress_vbox.append(self.progress_bar)
        
        self.status_label = Gtk.Label(label="Initializing restore...")
        self.status_label.add_css_class('title-3')
        progress_vbox.append(self.status_label)
        
        # Scrolled Text View for live logs
        log_scrolled = Gtk.ScrolledWindow()
        log_scrolled.set_vexpand(True)
        log_scrolled.add_css_class('log-view')
        
        self.text_view = Gtk.TextView()
        self.text_view.set_editable(False)
        self.text_view.set_cursor_visible(False)
        self.text_buffer = self.text_view.get_buffer()
        log_scrolled.set_child(self.text_view)
        progress_vbox.append(log_scrolled)
        
        self.done_btn = Gtk.Button(label="Done")
        self.done_btn.add_css_class("suggested-action")
        self.done_btn.set_halign(Gtk.Align.END)
        self.done_btn.set_visible(False)
        self.done_btn.connect('clicked', lambda _: self.close())
        progress_vbox.append(self.done_btn)
        
        self.stack.add_named(progress_vbox, "progress")

    def on_toggle_app(self, app, is_checked):
        key = app.get('id') or app.get('name')
        if is_checked:
            self.selected_ids.add(key)
        else:
            self.selected_ids.discard(key)
        self.counter_label.set_text(f"Selected: {len(self.selected_ids)} of {len(self.apps)} apps to restore")
        self.start_restore_btn.set_sensitive(len(self.selected_ids) > 0)

    def on_toggle_all(self, btn):
        if len(self.selected_ids) == len(self.apps):
            self.selected_ids.clear()
            self.select_all_btn.set_label("Select All")
        else:
            self.selected_ids = set(a.get('id') or a.get('name') for a in self.apps)
            self.select_all_btn.set_label("Deselect All")
        for key, row in self.row_widgets.items():
            row.check.set_active(key in self.selected_ids)
        self.counter_label.set_text(f"Selected: {len(self.selected_ids)} of {len(self.apps)} apps to restore")
        self.start_restore_btn.set_sensitive(len(self.selected_ids) > 0)

    def append_log(self, text):
        end_iter = self.text_buffer.get_end_iter()
        self.text_buffer.insert(end_iter, text + "\n")
        self.text_view.scroll_to_iter(self.text_buffer.get_end_iter(), 0.0, False, 0.0, 0.0)

    def on_start_restore(self, _):
        if not self.selected_ids:
            return
            
        self.stack.set_visible_child_name("progress")
        self.close_btn.set_sensitive(False)
        self.append_log(f"Starting restore from {os.path.basename(self.archive_path)}...")
        
        def progress_cb(step, total, msg):
            def update():
                frac = min(1.0, max(0.0, step / max(1, total)))
                self.progress_bar.set_fraction(frac)
                self.progress_bar.set_text(f"{int(frac * 100)}%")
                self.status_label.set_text(msg)
                self.append_log(msg)
            GLib.idle_add(update)

        def worker():
            success, logs = backup_manager.restore_backup_archive(
                self.archive_path, list(self.selected_ids), progress_callback=progress_cb
            )
            GLib.idle_add(self.on_restore_completed, success, logs)

        threading.Thread(target=worker, daemon=True).start()

    def on_restore_completed(self, success, logs):
        self.close_btn.set_sensitive(True)
        self.done_btn.set_visible(True)
        if success:
            self.status_label.set_text("✓ Restore Finished Successfully!")
            self.append_log("\n✓ All selected applications have been restored!")
            self.parent_window.show_toast("✓ Applications restored successfully!")
            self.parent_window.load_applications_async()
        else:
            self.status_label.set_text("Notice: Restore completed with warnings")
            self.append_log("\nRestore encountered some issues. See logs above.")

class LinuxAppManagerWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_title("Linux App Manager")
        self.set_default_size(900, 650)
        
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
        title_widget = Adw.WindowTitle(title="Linux App Manager", subtitle="Manage, Backup & Clone Applications")
        header.set_title_widget(title_widget)
        
        # Install File Button (Left)
        install_btn = Gtk.Button()
        install_content = Adw.ButtonContent(icon_name="list-add-symbolic", label="Install File")
        install_btn.set_child(install_content)
        install_btn.add_css_class("suggested-action")
        install_btn.set_tooltip_text("Install a .deb, Flatpak, or .AppImage package")
        install_btn.connect("clicked", lambda _: self.on_choose_install_file())
        header.pack_start(install_btn)
        
        # Header Buttons (Right)
        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Refresh Application List")
        refresh_btn.connect("clicked", lambda _: self.load_applications_async())
        header.pack_end(refresh_btn)
        
        restore_btn = Gtk.Button()
        restore_content = Adw.ButtonContent(icon_name="folder-download-symbolic", label="Restore")
        restore_btn.set_child(restore_content)
        restore_btn.set_tooltip_text("Restore applications or data from a .lam backup package")
        restore_btn.connect("clicked", lambda _: self.on_choose_restore_file())
        header.pack_end(restore_btn)
        
        backup_btn = Gtk.Button()
        backup_content = Adw.ButtonContent(icon_name="edit-copy-symbolic", label="Backup & Clone")
        backup_btn.set_child(backup_content)
        backup_btn.set_tooltip_text("Backup applications or clone complete environments with login data")
        backup_btn.connect("clicked", lambda _: self.open_backup_clone_dialog())
        header.pack_end(backup_btn)
        
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
            if not any(btn.get_active() for btn in self.filter_buttons.values()):
                self.filter_buttons['All'].set_active(True)

    def on_search_changed(self, entry):
        self.search_query = entry.get_text().strip().lower()
        self.render_app_list()

    def render_app_list(self):
        if not hasattr(self, 'list_box'):
            return
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
        self.load_applications_async()

    def on_uninstall_failed(self, name, error_msg, row_widget):
        row_widget.del_btn.set_sensitive(True)
        row_widget.open_btn.set_sensitive(True)
        
        if "Authentication failed" in error_msg or "cancelled" in error_msg.lower() or "not authorized" in error_msg.lower():
            self.show_toast(f"Uninstallation cancelled by user.")
        else:
            dialog = Adw.MessageDialog.new(self, f"Uninstallation Failed", None)
            dialog.set_body(f"Failed to remove {name}:\n\n{error_msg[:300]}")
            dialog.add_response("ok", "OK")
            dialog.present()

    def open_backup_clone_dialog(self):
        if not self.apps:
            self.show_toast("No applications loaded to backup.")
            return
        dlg = BackupCloneDialog(self, self.apps)
        dlg.present()

    def on_choose_restore_file(self):
        downloads = os.path.expanduser('~/Downloads')
        home = os.path.expanduser('~')
        start_dir = downloads if os.path.isdir(downloads) else home
        initial_folder = Gio.File.new_for_path(start_dir)

        if hasattr(Gtk, 'FileDialog'):
            dialog = Gtk.FileDialog.new()
            dialog.set_title("Select Backup Package to Restore")
            dialog.set_initial_folder(initial_folder)

            filter_lam = Gtk.FileFilter()
            filter_lam.set_name("Linux App Manager Backup (*.lam)")
            filter_lam.add_pattern("*.lam")

            filters_list = Gio.ListStore.new(Gtk.FileFilter)
            filters_list.append(filter_lam)
            dialog.set_filters(filters_list)

            def on_open_finish(dlg, result):
                try:
                    gfile = dlg.open_finish(result)
                    if gfile:
                        path = gfile.get_path()
                        if path and os.path.exists(path):
                            self.prompt_restore_archive(path)
                except Exception:
                    pass

            dialog.open(self, None, on_open_finish)
        else:
            chooser = Gtk.FileChooserNative.new(
                "Select Backup Package to Restore",
                self,
                Gtk.FileChooserAction.OPEN,
                "Restore",
                "Cancel"
            )
            chooser.set_current_folder(initial_folder)
            filter_lam = Gtk.FileFilter()
            filter_lam.set_name("Linux App Manager Backup (*.lam)")
            filter_lam.add_pattern("*.lam")
            chooser.add_filter(filter_lam)

            def on_response(dlg, response_id):
                if response_id == Gtk.ResponseType.ACCEPT:
                    gfile = dlg.get_file()
                    if gfile:
                        path = gfile.get_path()
                        if path and os.path.exists(path):
                            self.prompt_restore_archive(path)
                dlg.destroy()

            chooser.connect("response", on_response)
            chooser.show()

    def prompt_restore_archive(self, file_path):
        dlg = RestoreDialog(self, file_path)
        dlg.present()

    def on_choose_install_file(self):
        downloads = os.path.expanduser('~/Downloads')
        home = os.path.expanduser('~')
        start_dir = downloads if os.path.isdir(downloads) else home
        initial_folder = Gio.File.new_for_path(start_dir)

        if hasattr(Gtk, 'FileDialog'):
            dialog = Gtk.FileDialog.new()
            dialog.set_title("Select Package to Install")
            dialog.set_initial_folder(initial_folder)

            filter_all = Gtk.FileFilter()
            filter_all.set_name("All Supported Packages (*.deb, *.flatpak, *.flatpakref, *.AppImage, *.lam)")
            for pat in ["*.deb", "*.flatpak", "*.flatpakref", "*.AppImage", "*.appimage", "*.lam"]:
                filter_all.add_pattern(pat)

            filter_deb = Gtk.FileFilter()
            filter_deb.set_name("Debian Packages (*.deb)")
            filter_deb.add_pattern("*.deb")

            filter_flatpak = Gtk.FileFilter()
            filter_flatpak.set_name("Flatpak Packages (*.flatpak, *.flatpakref)")
            filter_flatpak.add_pattern("*.flatpak")
            filter_flatpak.add_pattern("*.flatpakref")

            filter_appimage = Gtk.FileFilter()
            filter_appimage.set_name("AppImages (*.AppImage)")
            filter_appimage.add_pattern("*.AppImage")
            filter_appimage.add_pattern("*.appimage")

            filters_list = Gio.ListStore.new(Gtk.FileFilter)
            filters_list.append(filter_all)
            filters_list.append(filter_deb)
            filters_list.append(filter_flatpak)
            filters_list.append(filter_appimage)
            dialog.set_filters(filters_list)
            dialog.set_default_filter(filter_all)

            def on_open_finish(dlg, result):
                try:
                    gfile = dlg.open_finish(result)
                    if gfile:
                        path = gfile.get_path()
                        if path and os.path.exists(path):
                            if path.lower().endswith('.lam'):
                                self.prompt_restore_archive(path)
                            else:
                                self.prompt_install_file(path)
                except Exception:
                    pass

            dialog.open(self, None, on_open_finish)
        else:
            chooser = Gtk.FileChooserNative.new(
                "Select Package to Install",
                self,
                Gtk.FileChooserAction.OPEN,
                "Install",
                "Cancel"
            )
            chooser.set_current_folder(initial_folder)

            filter_all = Gtk.FileFilter()
            filter_all.set_name("All Supported Packages (*.deb, *.flatpak, *.flatpakref, *.AppImage, *.lam)")
            for pat in ["*.deb", "*.flatpak", "*.flatpakref", "*.AppImage", "*.appimage", "*.lam"]:
                filter_all.add_pattern(pat)
            chooser.add_filter(filter_all)

            def on_response(dlg, response_id):
                if response_id == Gtk.ResponseType.ACCEPT:
                    gfile = dlg.get_file()
                    if gfile:
                        path = gfile.get_path()
                        if path and os.path.exists(path):
                            if path.lower().endswith('.lam'):
                                self.prompt_restore_archive(path)
                            else:
                                self.prompt_install_file(path)
                dlg.destroy()

            chooser.connect("response", on_response)
            chooser.show()

    def prompt_install_file(self, file_path):
        try:
            info = installer.inspect_package(file_path)
        except Exception as e:
            self.show_toast(f"Error reading package: {e}")
            return

        name = info.get('name', os.path.basename(file_path))
        pkg_type = info.get('type', 'Unknown')
        version = info.get('version', '')
        size = info.get('size', '')
        desc = info.get('description', '')

        dialog = Adw.MessageDialog.new(self, f"Install {name}?", None)
        body = f"<b>Type:</b> {pkg_type}\n<b>File:</b> {os.path.basename(file_path)}"
        if version:
            body += f"\n<b>Version:</b> {version}"
        if size:
            body += f"\n<b>Size:</b> {size}"
        if desc:
            body += f"\n\n{desc}"

        if info.get('requires_root'):
            body += "\n\n<i>(A system password prompt will appear to authorize installation)</i>"

        dialog.set_body(body)
        dialog.set_body_use_markup(True)

        dialog.add_response("cancel", "Cancel")
        dialog.add_response("install", "Install Package")
        dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("install")
        dialog.set_close_response("cancel")

        def on_response(dlg, response):
            if response == "install":
                self.execute_install(file_path, info)

        dialog.connect("response", on_response)
        dialog.present()

    def execute_install(self, file_path, info):
        name = info.get('name', 'Package')
        self.show_toast(f"Installing {name}... Please wait")

        def worker():
            success, msg = installer.install_package(file_path, info)
            if success:
                GLib.idle_add(self.on_install_success, name, msg)
            else:
                GLib.idle_add(self.on_install_failed, name, msg)

        threading.Thread(target=worker, daemon=True).start()

    def on_install_success(self, name, message):
        self.show_toast(f"✓ {name} installed successfully!", timeout=5)
        self.load_applications_async()

    def on_install_failed(self, name, error_msg):
        if "Authentication failed" in error_msg or "cancelled" in error_msg.lower() or "not authorized" in error_msg.lower():
            self.show_toast(f"Installation cancelled by user.")
        else:
            dialog = Adw.MessageDialog.new(self, f"Installation Failed", None)
            dialog.set_body(f"Failed to install {name}:\n\n{error_msg[:400]}")
            dialog.add_response("ok", "OK")
            dialog.present()

class LinuxAppManager(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="com.github.linuxappmanager.App",
            flags=Gio.ApplicationFlags.HANDLES_OPEN
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
        
        # Check if any file argument was provided via CLI
        for arg in sys.argv[1:]:
            if not arg.startswith('-') and os.path.exists(arg):
                path = os.path.abspath(arg)
                if path.lower().endswith('.lam'):
                    GLib.idle_add(win.prompt_restore_archive, path)
                else:
                    GLib.idle_add(win.prompt_install_file, path)
                break

    def do_open(self, *args):
        win = self.props.active_window
        if not win:
            win = LinuxAppManagerWindow(application=self)
        win.present()
        if args and len(args) > 0 and isinstance(args[0], (list, tuple)):
            files = args[0]
            if files:
                path = files[0].get_path()
                if path and os.path.exists(path):
                    if path.lower().endswith('.lam'):
                        GLib.idle_add(win.prompt_restore_archive, os.path.abspath(path))
                    else:
                        GLib.idle_add(win.prompt_install_file, os.path.abspath(path))

if __name__ == '__main__':
    app = LinuxAppManager()
    sys.exit(app.run(sys.argv))
