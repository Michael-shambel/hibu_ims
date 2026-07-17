# build.py
import os
import subprocess
import sys
import shutil
from pathlib import Path

def clean_build_dirs():
    """Remove previous build directories"""
    dirs_to_remove = ['build', 'dist', '__pycache__']
    for dir_name in dirs_to_remove:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"Removed {dir_name}/")
    
    # Remove .spec file
    spec_file = 'build.spec'
    if os.path.exists(spec_file):
        os.remove(spec_file)

def create_installer():
    """Create installer for the application"""
    print("Creating installer...")
    
    if sys.platform == "win32":
        # Create NSIS installer for Windows
        nsis_script = '''
        ; IMS Software Installer
        Outfile "IMS_Software_Setup.exe"
        InstallDir "$PROGRAMFILES\\IMS Software"
        Name "IMS Software"
        
        Section "Main"
            SetOutPath "$INSTDIR"
            File /r "dist\\IMS_Software\\*.*"
            
            ; Create desktop shortcut
            CreateShortCut "$DESKTOP\\IMS Software.lnk" "$INSTDIR\\IMS_Software.exe"
            
            ; Create start menu shortcut
            CreateDirectory "$SMPROGRAMS\\IMS Software"
            CreateShortCut "$SMPROGRAMS\\IMS Software\\IMS Software.lnk" "$INSTDIR\\IMS_Software.exe"
            CreateShortCut "$SMPROGRAMS\\IMS Software\\Uninstall.lnk" "$INSTDIR\\uninstall.exe"
            
            ; Write uninstaller
            WriteUninstaller "$INSTDIR\\uninstall.exe"
            
            ; Write registry keys
            WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\IMSSoftware" \
                "DisplayName" "IMS Software"
            WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\IMSSoftware" \
                "UninstallString" '"$INSTDIR\\uninstall.exe"'
            WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\IMSSoftware" \
                "DisplayIcon" "$INSTDIR\\IMS_Software.exe"
        SectionEnd
        
        Section "Uninstall"
            Delete "$DESKTOP\\IMS Software.lnk"
            Delete "$SMPROGRAMS\\IMS Software\\*.*"
            RMDir "$SMPROGRAMS\\IMS Software"
            RMDir /r "$INSTDIR"
            DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\IMSSoftware"
        SectionEnd
        '''
        
        with open('installer.nsi', 'w') as f:
            f.write(nsis_script)
        
        # Compile NSIS installer (requires NSIS installed)
        try:
            subprocess.run(['makensis', 'installer.nsi'], check=True)
            print("Installer created: IMS_Software_Setup.exe")
        except:
            print("NSIS not found. Install NSIS to create installer.")
    
    elif sys.platform == "darwin":
        # Create DMG for macOS
        print("Creating DMG for macOS...")
        # Use create-dmg if installed
        pass
    
    else:
        # Create AppImage for Linux
        print("Creating AppImage for Linux...")
        # Build process for Linux

def main():
    print("🚀 Building IMS Software...")
    
    # Clean previous builds
    clean_build_dirs()
    
    # Install requirements in virtual environment first
    print("Installing dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
    
    # Run PyInstaller
    print("Running PyInstaller...")
    
    # Use onefile for single executable or onedir for folder
    mode = "onefile"  # Change to "onedir" if you want folder distribution
    
    cmd = [
        "pyinstaller",
        "--clean",
        f"--{mode}",
        "--windowed",  # No console window
        "--icon=assets/logo.ico",
        "--name=IMS_Software",
        "--add-data=assets;assets",
        "--add-data=ui;ui",
        "--hidden-import=sqlalchemy.sql.default_comparator",
        "--hidden-import=pydantic",
        "--hidden-import=pydantic_core",
        "--exclude-module=matplotlib",
        "--exclude-module=pandas",
        "--exclude-module=numpy",
        "--upx-dir=/path/to/upx",  # Optional: for compression
        "main.py"
    ]
    
    # Add platform-specific options
    if sys.platform == "win32":
        cmd.append("--version-file=version_info.txt")
    
    subprocess.run(cmd, check=True)
    
    # Create version_info.txt for Windows (optional)
    if sys.platform == "win32" and not os.path.exists("version_info.txt"):
        with open("version_info.txt", "w") as f:
            f.write("""# UTF-8
#
# For more details about fixed file info 'ffi' see:
# http://msdn.microsoft.com/en-us/library/ms646997.aspx
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 0, 0, 0),
    prodvers=(1, 0, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'Your Company'),
        StringStruct(u'FileDescription', u'IMS Software'),
        StringStruct(u'FileVersion', u'1.0.0.0'),
        StringStruct(u'InternalName', u'IMS_Software'),
        StringStruct(u'LegalCopyright', u'Copyright © 2024'),
        StringStruct(u'OriginalFilename', u'IMS_Software.exe'),
        StringStruct(u'ProductName', u'IMS Software'),
        StringStruct(u'ProductVersion', u'1.0.0.0')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
""")
    
    print(f"\n✅ Build complete! Executable is in: dist/")
    
    # Optional: Create installer
    create_installer = input("\nCreate installer? (y/n): ").lower() == 'y'
    if create_installer:
        create_installer()

if __name__ == "__main__":
    main()