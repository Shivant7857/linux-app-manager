import os
import glob
import subprocess
import shutil
from typing import List, Dict, Any

# Critical system apps that must not be deleted to prevent breaking the system
CRITICAL_PACKAGES = {
    'zorin-desktop', 'gnome-shell', 'nautilus', 'gnome-control-center',
    'gdm3', 'systemd', 'xwayland', 'xorg', 'mutter', 'gnome-session',
    'zorin-appearance', 'zorin-os-default-settings', 'apt', 'dpkg',
    'zorin-os-upgrader', 'gnome-terminal'
}

def get_flatpak_apps() -> List[Dict[str, Any]]:
    apps = []
    if not shutil.which('flatpak'):
        return apps
    try:
        res = subprocess.run(
            ['flatpak', 'list', '--app', '--columns=application,name,version,size,description'],
            capture_output=True, text=True, check=True
        )
        for line in res.stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) >= 5:
                app_id, name, version, size, desc = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip(), parts[4].strip()
                apps.append({
                    'id': app_id,
                    'name': name or app_id,
                    'type': 'Flatpak',
                    'version': version,
                    'size': size,
                    'description': desc,
                    'icon': app_id,
                    'is_system': False,
                    'exec_cmd': f'flatpak run {app_id}',
                    'uninstall_cmd': f'flatpak uninstall -y {app_id}',
                    'requires_root': False
                })
    except Exception as e:
        print(f"Error fetching flatpaks: {e}")
    return apps

def get_snap_apps() -> List[Dict[str, Any]]:
    apps = []
    if not shutil.which('snap'):
        return apps
    try:
        res = subprocess.run(['snap', 'list'], capture_output=True, text=True, check=True)
        lines = res.stdout.strip().split('\n')[1:]
        ignored_snaps = {'bare', 'core', 'core18', 'core20', 'core22', 'core24', 'snapd', 'gtk-common-themes'}
        for line in lines:
            parts = line.split()
            if len(parts) >= 3:
                name, version, rev = parts[0], parts[1], parts[2]
                if name in ignored_snaps or name.startswith('gnome-') or name.startswith('mesa-'):
                    continue
                apps.append({
                    'id': name,
                    'name': name.capitalize(),
                    'type': 'Snap',
                    'version': version,
                    'size': '',
                    'description': f'Snap package: {name}',
                    'icon': name,
                    'is_system': False,
                    'exec_cmd': f'snap run {name}',
                    'uninstall_cmd': f'pkexec snap remove {name}',
                    'requires_root': True
                })
    except Exception as e:
        print(f"Error fetching snaps: {e}")
    return apps

def get_appimages() -> List[Dict[str, Any]]:
    apps = []
    search_dirs = [
        os.path.expanduser('~/Applications'),
        os.path.expanduser('~/Downloads'),
        os.path.expanduser('~/.local/bin'),
        os.path.expanduser('~'),
        '/opt'
    ]
    seen_paths = set()
    for sdir in search_dirs:
        if not os.path.exists(sdir):
            continue
        try:
            for entry in os.scandir(sdir):
                if entry.is_file() and entry.name.lower().endswith('.appimage'):
                    if entry.path in seen_paths:
                        continue
                    seen_paths.add(entry.path)
                    try:
                        sz_bytes = entry.stat().st_size
                        sz_mb = f"{sz_bytes / (1024*1024):.1f} MB"
                    except Exception:
                        sz_mb = ""
                    clean_name = entry.name[:-9].replace('-', ' ').replace('_', ' ').strip()
                    apps.append({
                        'id': entry.path,
                        'name': clean_name or entry.name,
                        'type': 'AppImage',
                        'version': '',
                        'size': sz_mb,
                        'description': f'AppImage file ({entry.path})',
                        'icon': 'application-x-executable',
                        'path': entry.path,
                        'is_system': False,
                        'exec_cmd': f'"{entry.path}"',
                        'uninstall_cmd': f'rm -f "{entry.path}"',
                        'requires_root': not os.access(os.path.dirname(entry.path), os.W_OK)
                    })
        except (PermissionError, FileNotFoundError):
            continue
    return apps

def get_dpkg_map() -> Dict[str, str]:
    """Batch query dpkg ownership for /usr/share/applications"""
    dpkg_map = {}
    try:
        res = subprocess.run(['dpkg', '-S', '/usr/share/applications/*.desktop'], capture_output=True, text=True)
        for line in res.stdout.splitlines():
            if ':' in line:
                pkg_part, path_part = line.split(':', 1)
                pkg = pkg_part.split(',')[0].strip() # handles multiarch like pkg:amd64
                if ':' in pkg:
                    pkg = pkg.split(':')[0]
                dpkg_map[path_part.strip()] = pkg
    except Exception:
        pass
    return dpkg_map

def get_deb_apps(flatpak_ids: set, snap_ids: set) -> List[Dict[str, Any]]:
    import gi
    gi.require_version('Gio', '2.0')
    from gi.repository import Gio
    
    dpkg_map = get_dpkg_map()
    apps = []
    all_app_infos = Gio.AppInfo.get_all()
    
    for app in all_app_infos:
        if not app.should_show():
            continue
            
        desktop_file = app.get_filename() or ''
        exec_str = app.get_executable() or ''
        app_id = app.get_id() or ''
        
        # Exclude flatpak and snap
        if 'flatpak' in desktop_file or 'flatpak' in exec_str:
            continue
        if 'snap' in desktop_file or 'snap' in exec_str or app_id in snap_ids:
            continue
        if '.appimage' in desktop_file.lower() or '.appimage' in exec_str.lower():
            continue
            
        icon = app.get_icon()
        icon_name = icon.to_string() if icon else 'application-x-executable'
        
        name = app.get_name() or app_id
        comment = app.get_description() or ''
        
        package_name = dpkg_map.get(desktop_file)
        is_system = False
        if package_name:
            if package_name in CRITICAL_PACKAGES or 'zorin-desktop' in package_name:
                is_system = True
        else:
            if 'settings' in app_id.lower() or 'control-center' in exec_str.lower():
                is_system = True
        
        uninstall_cmd = f'pkexec apt remove -y {package_name}' if package_name else f'pkexec rm -f "{desktop_file}"'
        
        apps.append({
            'id': app_id,
            'name': name,
            'type': 'Debian (.deb)',
            'version': '',
            'size': '',
            'description': comment,
            'icon': icon_name,
            'package_name': package_name,
            'is_system': is_system,
            'desktop_file': desktop_file,
            'exec_cmd': f'gtk-launch {app_id}' if app_id else exec_str,
            'uninstall_cmd': uninstall_cmd,
            'requires_root': True
        })
    return apps

def scan_all_applications() -> List[Dict[str, Any]]:
    flatpaks = get_flatpak_apps()
    flatpak_ids = {a['id'] for a in flatpaks}
    
    snaps = get_snap_apps()
    snap_ids = {a['id'] for a in snaps}
    
    appimages = get_appimages()
    debs = get_deb_apps(flatpak_ids, snap_ids)
    
    all_apps = flatpaks + snaps + appimages + debs
    all_apps.sort(key=lambda x: x['name'].lower())
    return all_apps

if __name__ == '__main__':
    import time
    t0 = time.time()
    apps = scan_all_applications()
    t1 = time.time()
    print(f"Total apps discovered: {len(apps)} in {t1 - t0:.2f}s")
