# create_package.py - Create professional distribution package
import os
import shutil
import json
from pathlib import Path
from datetime import datetime

def create_package():
    print("=" * 60)
    print("CREATING DISTRIBUTION PACKAGE")
    print("=" * 60)
    
    # Configuration
    app_name = "InventoryManager"
    version = "1.0.0"
    company = "YourCompany"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create package directory
    package_dir = Path(f"{app_name}_v{version}_{timestamp}")
    package_dir.mkdir(exist_ok=True)
    
    print(f"📦 Creating package: {package_dir.name}")
    
    # 1. Copy executable
    exe_src = Path("dist") / f"{app_name}.exe"
    if exe_src.exists():
        shutil.copy2(exe_src, package_dir / f"{app_name}.exe")
        print("✅ Copied executable")
    else:
        print("❌ Executable not found!")
        return False
    
    # 2. Create configuration files
    config_files = {
        "README.txt": f"""Inventory Management System v{version}
{'=' * 50}

INSTALLATION:
1. Extract all files to a folder (e.g., C:\\Program Files\\{app_name})
2. Run {app_name}.exe
3. On first run, admin credentials will be generated automatically
4. Check %%APPDATA%%\\{company}\\admin_credentials.txt for initial password

SYSTEM REQUIREMENTS:
- Windows 10/11 (64-bit)
- 4GB RAM minimum
- 500MB free disk space
- Internet connection (for Telegram/SMS features)

CONFIGURATION:
For API integration:
1. Copy 'config_template.ini' to 'config.ini'
2. Edit with your API keys
3. Restart the application

FEATURES:
✓ Inventory tracking
✓ Sales management
✓ Reporting
✓ Telegram notifications
✓ SMS alerts
✓ User management

SUPPORT:
Email: support@{company.lower()}.com
Phone: (123) 456-7890
Website: www.{company.lower()}.com

TROUBLESHOOTING:
1. If app doesn't start: Install Visual C++ Redistributable
2. If missing DLL: Reinstall the application
3. For database issues: Contact support

{'=' * 50}
© {datetime.now().year} {company}. All rights reserved.
""",
        
        "config_template.ini": f"""; {app_name} Configuration Template
; Copy this file to 'config.ini' and edit the values

[Application]
Name = {app_name}
Version = {version}
Company = {company}

[Database]
; SQLite is used by default
; Type = sqlite
; Path = %%APPDATA%%\\{company}\\database\\inventory.db

[Telegram]
; Get token from @BotFather
; BotToken = YOUR_BOT_TOKEN_HERE
; AdminIDs = 123456789,987654321  ; Comma-separated

[SMS]
; APIKey = YOUR_SMS_API_KEY_HERE
; SenderID = INVENTORY
; URL = https://api.example.com/sms

[Backup]
AutoBackup = true
BackupIntervalHours = 24
MaxBackups = 30

[Reports]
DefaultFormat = PDF
SaveLocation = %%APPDATA%%\\{company}\\reports
""",
        
        "uninstall.bat": f"""@echo off
echo Uninstalling {app_name}...
echo.

REM Stop application if running
taskkill /f /im {app_name}.exe 2>nul
timeout /t 2 /nobreak >nul

REM Remove application data (optional - user might want to keep)
set /p choice=Remove application data from %%APPDATA%%\\{company}? (Y/N): 
if /i "%choice%"=="Y" (
    rmdir /s /q "%APPDATA%\\{company}"
    echo Application data removed.
)

REM Remove shortcuts
del "%PUBLIC%\\Desktop\\{app_name}.lnk" 2>nul
del "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\{app_name}.lnk" 2>nul

echo.
echo {app_name} has been uninstalled.
echo You may now delete this folder.
pause
""",
        
        "install.bat": f"""@echo off
echo Installing {app_name} v{version}
echo.

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Please run as Administrator!
    pause
    exit /b 1
)

REM Create Start Menu shortcut
set SHORTCUT_DIR="%%APPDATA%%\\Microsoft\\Windows\\Start Menu\\Programs\\{company}"
if not exist %SHORTCUT_DIR% mkdir %SHORTCUT_DIR%

powershell -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT_DIR%\\{app_name}.lnk');$s.TargetPath='%%~dp0{app_name}.exe';$s.WorkingDirectory='%%~dp0';$s.Save()"

REM Create Desktop shortcut (optional)
set /p create_desktop=Create desktop shortcut? (Y/N): 
if /i "%%create_desktop%%"=="Y" (
    powershell -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%PUBLIC%\\Desktop\\{app_name}.lnk');$s.TargetPath='%%~dp0{app_name}.exe';$s.WorkingDirectory='%%~dp0';$s.Save()"
)

REM Create application data directory
if not exist "%%APPDATA%%\\{company}" mkdir "%%APPDATA%%\\{company}"
if not exist "%%APPDATA%%\\{company}\\database" mkdir "%%APPDATA%%\\{company}\\database"
if not exist "%%APPDATA%%\\{company}\\reports" mkdir "%%APPDATA%%\\{company}\\reports"
if not exist "%%APPDATA%%\\{company}\\logs" mkdir "%%APPDATA%%\\{company}\\logs"
if not exist "%%APPDATA%%\\{company}\\backups" mkdir "%%APPDATA%%\\{company}\\backups"

echo.
echo Installation complete!
echo.
echo Next steps:
echo 1. Run {app_name}.exe
echo 2. Login with admin credentials from %%APPDATA%%\\{company}\\admin_credentials.txt
echo.
pause
"""
    }
    
    # Create files
    for filename, content in config_files.items():
        filepath = package_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Created {filename}")
    
    # 3. Create version info
    version_info = {
        "application": app_name,
        "version": version,
        "build_date": timestamp,
        "company": company,
        "files": {
            "executable": f"{app_name}.exe",
            "readme": "README.txt",
            "config_template": "config_template.ini",
            "installer": "install.bat",
            "uninstaller": "uninstall.bat"
        },
        "requirements": {
            "os": "Windows 10/11 64-bit",
            "ram": "4GB minimum",
            "storage": "500MB free space",
            "dependencies": "Visual C++ Redistributable"
        }
    }
    
    with open(package_dir / "version.json", 'w') as f:
        json.dump(version_info, f, indent=2)
    print("✅ Created version.json")
    
    # 4. Copy assets folder (if needed for documentation)
    assets_src = Path("assets")
    if assets_src.exists():
        assets_dest = package_dir / "assets"
        shutil.copytree(assets_src, assets_dest, dirs_exist_ok=True)
        print("✅ Copied assets folder")
    
    # 5. Create zip file
    print("\n📦 Creating ZIP archive...")
    zip_filename = f"{app_name}_v{version}_{timestamp}.zip"
    shutil.make_archive(
        f"{app_name}_v{version}_{timestamp}",
        'zip',
        package_dir
    )
    
    zip_size = Path(zip_filename).stat().st_size / (1024 * 1024)
    
    print("\n" + "=" * 60)
    print("🎉 PACKAGE CREATED SUCCESSFULLY!")
    print("=" * 60)
    print(f"\n📁 Package folder: {package_dir}")
    print(f"📦 ZIP archive: {zip_filename} ({zip_size:.1f} MB)")
    
    print("\n📋 Contents:")
    for item in sorted(package_dir.iterdir()):
        if item.is_file():
            size = item.stat().st_size / 1024
            print(f"  • {item.name} ({size:.1f} KB)")
    
    print("\n🚀 Next steps:")
    print("1. Test the package on a clean Windows VM")
    print("2. Create proper installer with Inno Setup")
    print("3. Sign the executable with code signing certificate")
    print("4. Upload to distribution channels")
    
    return True

if __name__ == "__main__":
    create_package()