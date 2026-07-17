import os
import sys
import shutil
from pathlib import Path
from datetime import datetime

def is_frozen():
    """Check if running as compiled .exe"""
    return getattr(sys, 'frozen', False)

def get_appdata_dir():
    """
    Get AppData directory that PERSISTS after app closes.
    Windows: %APPDATA%\InventorySystem\
    Development: project_root\
    """
    if is_frozen():
        # PRODUCTION: Running as .exe
        if os.name == 'nt':
            appdata = os.getenv('APPDATA')
            if not appdata:
                username = os.getenv('USERNAME', 'User')
                appdata = f"C:\\Users\\{username}\\AppData\\Roaming"
            app_dir = Path(appdata) / 'InventorySystem'
        else:
            app_dir = Path.home() / '.inventory_system'
        
        # Create directory structure
        for subdir in ['database', 'reports', 'logs', 'config', 'backups']:
            (app_dir / subdir).mkdir(parents=True, exist_ok=True)
        
        return app_dir
    else:
        # DEVELOPMENT: Running from source
        return Path(__file__).parent

def resource_path(relative_path):
    """
    UPDATED: Get path for resources.
    - Read-only files (images, UI): Use PyInstaller temp or project folder
    - Writable files (.db, .json): ALWAYS use AppData when .exe
    """
    # Check if it's a writable file
    is_writable = relative_path.endswith(('.db', '.json', '.log', '.txt', '.pdf', '.xlsx', '.csv'))
    
    if is_writable and is_frozen():
        # Writable files in PRODUCTION: Use AppData
        base_dir = get_appdata_dir()
        
        # Organize by file type
        if relative_path.endswith('.db'):
            subdir = 'database'
        elif relative_path.endswith('.json'):
            subdir = 'database'  # or 'config'
        elif relative_path.endswith(('.pdf', '.xlsx', '.csv')):
            subdir = 'reports'
        elif relative_path.endswith('.log'):
            subdir = 'logs'
        else:
            subdir = ''
        
        if subdir:
            path = base_dir / subdir / relative_path
        else:
            path = base_dir / relative_path
        
        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)
    
    else:
        # Read-only resources or development mode
        try:
            # PyInstaller .exe: Use temp folder
            base_path = Path(sys._MEIPASS)
        except AttributeError:
            # Development: Use project folder
            base_path = Path(__file__).parent
        
        return str(base_path / relative_path)

# Convenience functions for specific file types
def get_database_path(db_name="inventory.db"):
    """Get path for database files"""
    if is_frozen():
        base = get_appdata_dir() / 'database'
    else:
        base = Path(__file__).parent / 'database'
    
    base.mkdir(exist_ok=True)
    return str(base / db_name)

def get_json_path(json_name):
    """Get path for JSON files"""
    if is_frozen():
        base = get_appdata_dir() / 'database'
    else:
        base = Path(__file__).parent / 'database'
    
    base.mkdir(exist_ok=True)
    return str(base / json_name)

def get_report_path(report_name):
    """Get path for report files"""
    if is_frozen():
        base = get_appdata_dir() / 'reports'
    else:
        base = Path(__file__).parent / 'reports'
    
    base.mkdir(exist_ok=True)
    return str(base / report_name)


def get_backup_dir():
    """Get path for database backups."""
    if is_frozen():
        base = get_appdata_dir() / 'backups'
    else:
        base = Path(__file__).parent / 'backups'

    base.mkdir(parents=True, exist_ok=True)
    return str(base)


def _prune_old_backups(backup_dir, max_backups=30):
    if max_backups is None or max_backups <= 0:
        return

    backup_path = Path(backup_dir)
    backups = sorted(
        backup_path.glob('db_backup_*.db'),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    for old_backup in backups[max_backups:]:
        try:
            old_backup.unlink()
        except OSError:
            pass


def backup_database(db_name='inventory.db', source_path=None, backup_dir=None, max_backups=30):
    """Copy the active SQLite database into the backups directory."""
    source = Path(source_path) if source_path else Path(get_database_path(db_name))
    if not source.exists():
        raise FileNotFoundError(f'Database file not found at {source}')

    backup_base = Path(backup_dir) if backup_dir else Path(get_backup_dir())
    backup_base.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = backup_base / f'db_backup_{timestamp}.db'
    shutil.copy2(source, backup_file)
    _prune_old_backups(backup_base, max_backups=max_backups)
    return str(backup_file)

# Test function
if __name__ == "__main__":
    print("🔧 UTILS.PY TEST")
    print("=" * 60)
    print(f"Frozen: {is_frozen()}")
    print(f"AppData dir: {get_appdata_dir()}")
    print(f"DB path: {get_database_path()}")
    print(f"JSON path: {get_json_path('test.json')}")
    print("=" * 60)
