import os
import subprocess
import shutil
import configparser
from typing import Dict, Any, Tuple

def format_size(bytes_sz: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_sz < 1024.0:
            return f"{bytes_sz:.1f} {unit}"
        bytes_sz /= 1024.0
    return f"{bytes_sz:.1f} TB"

def inspect_package(file_path: str) -> Dict[str, Any]:
    file_path = os.path.abspath(file_path)
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    file_size_bytes = os.path.getsize(file_path)
    formatted_size = format_size(file_size_bytes)
    basename = os.path.basename(file_path)
    lower_name = basename.lower()

    info = {
        'path': file_path,
        'filename': basename,
        'size': formatted_size,
        'type': 'Unknown',
        'name': basename,
        'version': '',
        'description': '',
        'icon': 'application-x-executable',
        'requires_root': False
    }

    if lower_name.endswith('.deb'):
        info['type'] = 'Debian (.deb)'
        info['icon'] = 'package-x-generic'
        info['requires_root'] = True
        try:
            # Extract fields using dpkg-deb -f
            res = subprocess.run(
                ['dpkg-deb', '-f', file_path, 'Package', 'Version', 'Architecture', 'Description'],
                capture_output=True, text=True, check=True
            )
            fields = {}
            current_field = None
            for line in res.stdout.splitlines():
                if ': ' in line and not line.startswith(' '):
                    k, v = line.split(': ', 1)
                    current_field = k.strip().lower()
                    fields[current_field] = v.strip()
                elif current_field and line.startswith(' '):
                    fields[current_field] += ' ' + line.strip()

            info['name'] = fields.get('package', basename)
            info['version'] = fields.get('version', '')
            desc = fields.get('description', '')
            info['description'] = desc.split('\n')[0] if desc else 'Debian software package'
        except Exception as e:
            info['description'] = f"Debian package ({basename})"

    elif lower_name.endswith('.flatpakref'):
        info['type'] = 'Flatpak Reference'
        info['icon'] = 'package-x-generic'
        info['requires_root'] = False
        try:
            cfg = configparser.ConfigParser(interpolation=None)
            cfg.read(file_path, encoding='utf-8')
            if 'Flatpak Ref' in cfg:
                ref = cfg['Flatpak Ref']
                info['name'] = ref.get('Name', basename[:-11])
                info['version'] = ref.get('Branch', '')
                info['description'] = f"Flatpak application reference from {ref.get('Url', 'remote repository')}"
        except Exception:
            info['description'] = 'Flatpak reference file'

    elif lower_name.endswith('.flatpak'):
        info['type'] = 'Flatpak Bundle'
        info['icon'] = 'package-x-generic'
        info['requires_root'] = False
        info['name'] = basename[:-8].replace('-', ' ').title()
        info['description'] = 'Flatpak standalone bundle'

    elif lower_name.endswith('.appimage'):
        info['type'] = 'AppImage'
        info['icon'] = 'application-x-executable'
        info['requires_root'] = False
        clean_name = basename[:-9].replace('-', ' ').replace('_', ' ').strip().title()
        info['name'] = clean_name or basename
        info['description'] = 'Portable Linux AppImage executable'

    else:
        info['description'] = 'Binary or package file'

    return info

def install_package(file_path: str, pkg_info: Dict[str, Any]) -> Tuple[bool, str]:
    file_path = os.path.abspath(file_path)
    pkg_type = pkg_info.get('type', '')

    if 'Debian' in pkg_type:
        # apt install automatically resolves local deb dependencies
        cmd = ['pkexec', 'apt', 'install', '-y', file_path]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                return True, f"Successfully installed {pkg_info['name']} via APT!"
            else:
                err = res.stderr.strip() or res.stdout.strip() or "Installation was cancelled or failed."
                return False, err
        except Exception as e:
            return False, str(e)

    elif 'Flatpak' in pkg_type:
        is_ref = file_path.lower().endswith('.flatpakref')
        if is_ref:
            cmd = ['flatpak', 'install', '--from', '-y', file_path]
        else:
            cmd = ['flatpak', 'install', '-y', file_path]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                return True, f"Successfully installed {pkg_info['name']} via Flatpak!"
            else:
                err = res.stderr.strip() or res.stdout.strip() or "Flatpak install failed."
                return False, err
        except Exception as e:
            return False, str(e)

    elif 'AppImage' in pkg_type:
        try:
            apps_dir = os.path.expanduser('~/Applications')
            os.makedirs(apps_dir, exist_ok=True)
            dest_path = os.path.join(apps_dir, pkg_info['filename'])

            # Copy if not already inside ~/Applications
            if os.path.abspath(file_path) != os.path.abspath(dest_path):
                shutil.copy2(file_path, dest_path)

            # chmod +x
            os.chmod(dest_path, os.stat(dest_path).st_mode | 0o111)

            # Generate a .desktop shortcut in ~/.local/share/applications/
            local_apps_dir = os.path.expanduser('~/.local/share/applications')
            os.makedirs(local_apps_dir, exist_ok=True)

            slug = pkg_info['name'].lower().replace(' ', '-')
            desktop_filename = f"appimage-{slug}.desktop"
            desktop_path = os.path.join(local_apps_dir, desktop_filename)

            desktop_content = f"""[Desktop Entry]
Name={pkg_info['name']}
Comment={pkg_info.get('description', 'AppImage Application')}
Exec="{dest_path}" %U
Icon=application-x-executable
Terminal=false
Type=Application
Categories=Utility;Application;
StartupNotify=true
"""
            with open(desktop_path, 'w', encoding='utf-8') as f:
                f.write(desktop_content)

            # Update desktop database
            subprocess.run(['update-desktop-database', local_apps_dir], capture_output=True)

            return True, f"✓ {pkg_info['name']} installed to ~/Applications and added to your Application Menu!"
        except Exception as e:
            return False, str(e)

    else:
        return False, f"Unsupported package format: {pkg_type}"
