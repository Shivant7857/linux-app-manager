import os
import re
import json
import shutil
import tarfile
import subprocess
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional, Callable

EXCLUDE_PATTERNS = [
    r'[Cc]ache',
    r'GPUCache',
    r'ShaderCache',
    r'Code Cache',
    r'blob_storage',
    r'[Cc]rashpad',
    r'Crash Reports',
    r'Service Worker[/\\]CacheStorage',
    r'Service Worker[/\\]ScriptCache',
    r'\.tmp$',
    r'\.temp$',
    r'\.log$',
    r'\.old$',
    r'\.bak$'
]

EXCLUDE_REGEX = re.compile('|'.join(EXCLUDE_PATTERNS))

def should_exclude(path: str) -> bool:
    """Check if file or directory matches cache/temp patterns."""
    return bool(EXCLUDE_REGEX.search(path))

def _slugify(text: str) -> str:
    """Normalize names for path matching (e.g. 'Google Chrome' -> 'google-chrome')."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9_-]+', '-', text).strip('-')
    return text

def discover_app_data_paths(app: Dict[str, Any]) -> List[Tuple[str, str]]:
    """
    Find relevant config and data paths for an application.
    Returns list of tuples: (absolute_path_on_disk, relative_archive_dest_folder)
    """
    home = os.path.expanduser('~')
    app_type = app.get('type', '')
    app_id = app.get('id', '')
    app_name = app.get('name', '')
    pkg_name = app.get('package_name', '')
    
    paths = []
    
    if app_type == 'Flatpak':
        # Flatpak keeps all config, data, and sandbox state in ~/.var/app/<app_id>
        var_path = os.path.join(home, '.var', 'app', app_id)
        if os.path.isdir(var_path):
            paths.append((var_path, f"flatpak/{app_id}"))
            
    elif app_type == 'Snap':
        # Snap stores user data in ~/snap/<snap_name>
        snap_path = os.path.join(home, 'snap', app_id)
        if os.path.isdir(snap_path):
            paths.append((snap_path, f"snap/{app_id}"))
            
    elif 'Debian' in app_type or app_type == 'AppImage':
        # Search candidate folder names in ~/.config and ~/.local/share
        candidates = set()
        for candidate in [app_id, pkg_name, app_name, _slugify(app_name)]:
            if candidate:
                candidate_clean = candidate.lower().strip()
                candidates.add(candidate_clean)
                candidates.add(candidate_clean.replace('-', ''))
                candidates.add(candidate_clean.replace('_', ''))
                # Handle prefixes/suffixes like google-chrome-stable -> google-chrome
                if candidate_clean.endswith('-stable'):
                    candidates.add(candidate_clean[:-7])
                if candidate_clean.endswith('-beta'):
                    candidates.add(candidate_clean[:-5])

        # Common known application alias mappings
        known_aliases = {
            'code': ['Code', 'VSCodium'],
            'vscode': ['Code'],
            'google-chrome': ['google-chrome'],
            'google-chrome-stable': ['google-chrome'],
            'chromium': ['chromium'],
            'brave-browser': ['BraveSoftware'],
            'firefox': ['mozilla/firefox'],
            'thunderbird': ['thunderbird'],
            'vlc': ['vlc'],
            'gimp': ['GIMP'],
            'discord': ['discord'],
            'spotify': ['spotify'],
            'obs-studio': ['obs-studio'],
            'telegram': ['TelegramDesktop'],
            'libreoffice': ['libreoffice'],
        }
        for cand in list(candidates):
            if cand in known_aliases:
                candidates.update(known_aliases[cand])

        # Check ~/.config
        config_dir = os.path.join(home, '.config')
        if os.path.isdir(config_dir):
            for cand in candidates:
                cand_path = os.path.join(config_dir, cand)
                if os.path.isdir(cand_path) and (cand_path, f"config/{cand}") not in paths:
                    paths.append((cand_path, f"config/{cand}"))

        # Check ~/.local/share
        share_dir = os.path.join(home, '.local', 'share')
        if os.path.isdir(share_dir):
            for cand in candidates:
                cand_path = os.path.join(share_dir, cand)
                if os.path.isdir(cand_path) and (cand_path, f"local_share/{cand}") not in paths:
                    paths.append((cand_path, f"local_share/{cand}"))
                    
    return paths

def calculate_paths_size(paths: List[Tuple[str, str]]) -> int:
    """Calculate total byte size for a list of paths, filtering out cache files."""
    total_size = 0
    for disk_path, _ in paths:
        if os.path.isfile(disk_path):
            total_size += os.path.getsize(disk_path)
        elif os.path.isdir(disk_path):
            for root, dirs, files in os.walk(disk_path):
                # Filter out cache dirs during walk
                dirs[:] = [d for d in dirs if not should_exclude(os.path.join(root, d))]
                for f in files:
                    fp = os.path.join(root, f)
                    if not should_exclude(fp):
                        try:
                            total_size += os.path.getsize(fp)
                        except (OSError, FileNotFoundError):
                            pass
    return total_size

def format_size(bytes_sz: int) -> str:
    """Format bytes into readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_sz < 1024.0:
            return f"{bytes_sz:.1f} {unit}"
        bytes_sz /= 1024.0
    return f"{bytes_sz:.1f} TB"

def get_app_data_summary(app: Dict[str, Any]) -> Tuple[int, str]:
    """Returns (size_in_bytes, formatted_size_str) for app's data."""
    paths = discover_app_data_paths(app)
    if not paths:
        return 0, "No data found"
    sz = calculate_paths_size(paths)
    return sz, format_size(sz)

def create_backup_archive(
    selected_apps: List[Dict[str, Any]],
    mode: str, # 'backup' or 'clone'
    output_path: str,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> Tuple[bool, str]:
    """
    Creates a .lam archive (tar.gz) containing manifest, AppImages, and (if clone mode) configuration/data.
    """
    output_path = os.path.abspath(output_path)
    if not output_path.endswith('.lam'):
        output_path += '.lam'
        
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    temp_dir = os.path.join(os.path.dirname(output_path), f".lam_tmp_{os.getpid()}")
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)
    
    total_steps = len(selected_apps) + 2
    current_step = 0
    
    def report(step: int, msg: str):
        if progress_callback:
            progress_callback(step, total_steps, msg)

    try:
        report(current_step, "Preparing package manifest...")
        
        manifest = {
            'format': 'linux-app-manager-backup',
            'version': '1.0',
            'mode': mode, # 'backup' (apps only) or 'clone' (apps + data)
            'created_at': datetime.now().isoformat(),
            'total_apps': len(selected_apps),
            'apps': []
        }
        
        # Open tar archive directly
        with tarfile.open(output_path, "w:gz") as tar:
            for app in selected_apps:
                current_step += 1
                app_name = app.get('name', 'App')
                app_type = app.get('type', '')
                report(current_step, f"Processing {app_name} ({app_type})...")
                
                app_record = {
                    'id': app.get('id', ''),
                    'name': app_name,
                    'type': app_type,
                    'version': app.get('version', ''),
                    'description': app.get('description', ''),
                    'package_name': app.get('package_name', ''),
                    'data_entries': []
                }
                
                # If AppImage, include the binary in the archive
                if app_type == 'AppImage':
                    appimage_src = app.get('path', '')
                    if appimage_src and os.path.isfile(appimage_src):
                        archive_ai_name = f"appimages/{os.path.basename(appimage_src)}"
                        tar.add(appimage_src, arcname=archive_ai_name)
                        app_record['appimage_file'] = archive_ai_name
                        
                # If Clone mode, include discovered config & data paths
                if mode == 'clone':
                    data_paths = discover_app_data_paths(app)
                    for disk_path, arc_rel in data_paths:
                        arc_full = f"data/{arc_rel}"
                        if os.path.exists(disk_path):
                            # Filter exclusions during tar add
                            def tar_filter(tarinfo):
                                if should_exclude(tarinfo.name):
                                    return None
                                return tarinfo
                            
                            tar.add(disk_path, arcname=arc_full, filter=tar_filter)
                            app_record['data_entries'].append({
                                'source_type': arc_rel.split('/')[0],
                                'archive_path': arc_full,
                                'original_path': disk_path
                            })
                            
                manifest['apps'].append(app_record)

            # Write manifest.json into the archive
            current_step += 1
            report(current_step, "Finalizing archive package...")
            manifest_file = os.path.join(temp_dir, 'manifest.json')
            with open(manifest_file, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2)
            tar.add(manifest_file, arcname='manifest.json')

        report(total_steps, "Backup created successfully!")
        return True, f"Successfully created {mode.capitalize()} archive:\n{output_path}"
        
    except Exception as e:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass
        return False, f"Failed to create backup: {str(e)}"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def inspect_backup_archive(archive_path: str) -> Dict[str, Any]:
    """
    Inspects a .lam archive and returns manifest details.
    """
    archive_path = os.path.abspath(archive_path)
    if not os.path.isfile(archive_path):
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    with tarfile.open(archive_path, "r:gz") as tar:
        try:
            manifest_member = tar.getmember('manifest.json')
        except KeyError:
            raise ValueError("Invalid Linux App Manager backup: missing manifest.json")
            
        f = tar.extractfile(manifest_member)
        if not f:
            raise ValueError("Failed to read manifest.json from archive")
        manifest = json.loads(f.read().decode('utf-8'))
        manifest['archive_path'] = archive_path
        manifest['archive_size'] = format_size(os.path.getsize(archive_path))
        return manifest

def restore_backup_archive(
    archive_path: str,
    selected_app_ids: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> Tuple[bool, List[str]]:
    """
    Restores selected applications and (if present) data from a .lam archive.
    """
    archive_path = os.path.abspath(archive_path)
    manifest = inspect_backup_archive(archive_path)
    
    apps_to_restore = manifest.get('apps', [])
    if selected_app_ids is not None:
        selected_set = set(selected_app_ids)
        apps_to_restore = [a for a in apps_to_restore if a.get('id') in selected_set or a.get('name') in selected_set]
        
    total_steps = len(apps_to_restore) + 1
    current_step = 0
    logs = []
    
    home = os.path.expanduser('~')
    
    def report(step: int, msg: str):
        logs.append(msg)
        if progress_callback:
            progress_callback(step, total_steps, msg)

    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            for app in apps_to_restore:
                current_step += 1
                name = app.get('name', 'Application')
                app_type = app.get('type', '')
                report(current_step, f"Restoring {name} ({app_type})...")
                
                # 1. Install or place application
                if app_type == 'Flatpak':
                    app_id = app.get('id')
                    if app_id:
                        # Check if already installed
                        check = subprocess.run(['flatpak', 'info', app_id], capture_output=True)
                        if check.returncode != 0:
                            report(current_step, f"Installing {name} via Flatpak...")
                            res = subprocess.run(['flatpak', 'install', '-y', 'flathub', app_id], capture_output=True, text=True)
                            if res.returncode == 0:
                                logs.append(f"✓ Installed Flatpak: {name}")
                            else:
                                logs.append(f"Notice: Flatpak install for {app_id}: {res.stderr.strip() or 'Failed'}")
                        else:
                            logs.append(f"✓ {name} is already installed.")
                            
                elif app_type == 'Snap':
                    snap_id = app.get('id')
                    if snap_id:
                        check = subprocess.run(['snap', 'list', snap_id], capture_output=True)
                        if check.returncode != 0:
                            report(current_step, f"Installing {name} via Snap...")
                            res = subprocess.run(['pkexec', 'snap', 'install', snap_id], capture_output=True, text=True)
                            if res.returncode == 0:
                                logs.append(f"✓ Installed Snap: {name}")
                            else:
                                logs.append(f"Notice: Snap install for {snap_id}: {res.stderr.strip() or 'Failed'}")
                        else:
                            logs.append(f"✓ {name} is already installed.")
                            
                elif 'Debian' in app_type:
                    pkg_name = app.get('package_name')
                    if pkg_name:
                        check = subprocess.run(['dpkg', '-s', pkg_name], capture_output=True)
                        if check.returncode != 0:
                            report(current_step, f"Installing {name} via APT...")
                            res = subprocess.run(['pkexec', 'apt', 'install', '-y', pkg_name], capture_output=True, text=True)
                            if res.returncode == 0:
                                logs.append(f"✓ Installed Debian package: {pkg_name}")
                            else:
                                logs.append(f"Notice: APT install for {pkg_name}: {res.stderr.strip() or 'Failed'}")
                        else:
                            logs.append(f"✓ {name} is already installed.")
                            
                elif app_type == 'AppImage':
                    ai_file = app.get('appimage_file')
                    if ai_file:
                        try:
                            member = tar.getmember(ai_file)
                            apps_dir = os.path.expanduser('~/Applications')
                            os.makedirs(apps_dir, exist_ok=True)
                            target_dest = os.path.join(apps_dir, os.path.basename(ai_file))
                            
                            with tar.extractfile(member) as src, open(target_dest, 'wb') as dst:
                                shutil.copyfileobj(src, dst)
                                
                            os.chmod(target_dest, os.stat(target_dest).st_mode | 0o111)
                            
                            # Create desktop shortcut
                            local_apps_dir = os.path.expanduser('~/.local/share/applications')
                            os.makedirs(local_apps_dir, exist_ok=True)
                            slug = name.lower().replace(' ', '-')
                            desktop_path = os.path.join(local_apps_dir, f"appimage-{slug}.desktop")
                            with open(desktop_path, 'w', encoding='utf-8') as df:
                                df.write(f"""[Desktop Entry]
Name={name}
Comment={app.get('description', 'AppImage Application')}
Exec="{target_dest}" %U
Icon=application-x-executable
Terminal=false
Type=Application
Categories=Utility;Application;
StartupNotify=true
""")
                            subprocess.run(['update-desktop-database', local_apps_dir], capture_output=True)
                            logs.append(f"✓ Restored AppImage {name} to ~/Applications")
                        except Exception as e:
                            logs.append(f"Error restoring AppImage {name}: {e}")
                            
                # 2. If Clone data entries exist, restore them to the right places
                data_entries = app.get('data_entries', [])
                if data_entries:
                    report(current_step, f"Restoring data & logins for {name}...")
                    for entry in data_entries:
                        arc_path = entry.get('archive_path')
                        orig_path = entry.get('original_path')
                        src_type = entry.get('source_type')
                        
                        try:
                            # Target destination resolution
                            if orig_path:
                                target_dest = orig_path
                            elif src_type == 'flatpak':
                                target_dest = os.path.join(home, '.var', 'app', app.get('id', ''))
                            elif src_type == 'snap':
                                target_dest = os.path.join(home, 'snap', app.get('id', ''))
                            elif src_type == 'config':
                                target_dest = os.path.join(home, '.config', os.path.basename(arc_path))
                            elif src_type == 'local_share':
                                target_dest = os.path.join(home, '.local', 'share', os.path.basename(arc_path))
                            else:
                                continue
                                
                            os.makedirs(os.path.dirname(target_dest), exist_ok=True)
                            
                            # Extract all matching archive members for this data entry
                            prefix = arc_path if arc_path.endswith('/') else arc_path + '/'
                            members_to_extract = []
                            for m in tar.getmembers():
                                if m.name == arc_path or m.name.startswith(prefix):
                                    members_to_extract.append(m)
                                    
                            for m in members_to_extract:
                                rel = os.path.relpath(m.name, arc_path)
                                if rel == '.':
                                    dest_item = target_dest
                                else:
                                    dest_item = os.path.join(target_dest, rel)
                                    
                                if m.isdir():
                                    os.makedirs(dest_item, exist_ok=True)
                                elif m.isfile():
                                    os.makedirs(os.path.dirname(dest_item), exist_ok=True)
                                    with tar.extractfile(m) as f_src, open(dest_item, 'wb') as f_dst:
                                        shutil.copyfileobj(f_src, f_dst)
                                        
                            logs.append(f"✓ Restored config data for {name} -> {target_dest}")
                        except Exception as e:
                            logs.append(f"Notice: Could not restore data for {name}: {e}")

        report(total_steps, "All selected applications restored!")
        return True, logs
    except Exception as e:
        return False, [f"Error restoring backup: {str(e)}"]
