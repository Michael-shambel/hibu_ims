# build_now.py - with cryptography support
import subprocess
import sys
import os

print("=" * 60)
print("STARTING BUILD...")
print("=" * 60)

# Clean first
print("🧹 Cleaning...")
os.system('rmdir /s /q dist build 2>nul')
os.system('del /q *.spec 2>nul')

# Build command
print("\n🔨 Building...")
cmd = [
    sys.executable, "-m", "PyInstaller",

    # Build options
    "--onefile",
    "--windowed",
    "--clean",
    "--noconfirm",
    "--name=InventoryManager",

    # Data folders to include
    "--add-data=models;models",
    "--add-data=services;services",
    "--add-data=security;security",
    "--add-data=ui;ui",
    "--add-data=assets;assets",

    # Exclude tkinter to avoid _Padding error
    "--exclude-module=tkinter",
    "--exclude-module=Tkinter",

    # Hidden imports
    "--hidden-import=sqlalchemy",
    "--hidden-import=sqlalchemy.dialects.sqlite",
    "--hidden-import=PySide6",
    "--hidden-import=apscheduler",

    # Cryptography hidden imports
    "--hidden-import=cryptography",
    "--hidden-import=cryptography.hazmat",
    "--hidden-import=cryptography.hazmat.backends",
    "--hidden-import=cryptography.hazmat.backends.default_backend",
    "--hidden-import=cryptography.hazmat.primitives",
    "--hidden-import=cryptography.hazmat.primitives.asymmetric",
    "--hidden-import=cryptography.hazmat.primitives.asymmetric.padding",
    "--hidden-import=cryptography.hazmat.primitives.hashes",

    # Collect all cryptography files (DLLs, etc.)
    "--collect-all=cryptography",

    # Main entry point
    "main.py"
]

# Add icon if exists
if os.path.exists("assets/logo.ico"):
    cmd.append("--icon=assets/logo.ico")

print(f"Running PyInstaller... (this may take 5-10 minutes)")

# Run and capture output
result = subprocess.run(
    cmd, 
    capture_output=True, 
    text=True,
    timeout=600  # 10 minute timeout
)

print("\n" + "=" * 60)
print("BUILD COMPLETE")
print("=" * 60)

if result.returncode == 0:
    print("✅ BUILD SUCCESSFUL!")
    
    # Check if executable exists
    if os.path.exists("dist/InventoryManager.exe"):
        size = os.path.getsize("dist/InventoryManager.exe") / (1024 * 1024)
        print(f"📁 Output: dist/InventoryManager.exe")
        print(f"📊 Size: {size:.2f} MB")
        print("\n🎉 Ready for distribution!")
    else:
        print("⚠️  Executable not found in dist/")
        
else:
    print("❌ BUILD FAILED!")
    print("\nLast 20 lines of output:")
    lines = result.stdout.split('\n')[-20:]
    for line in lines:
        if line.strip():
            print(f"  {line}")
    
    print("\nErrors:")
    lines = result.stderr.split('\n')[-20:]
    for line in lines:
        if line.strip() and "error" in line.lower():
            print(f"  ❌ {line}")

print("\n" + "=" * 60)