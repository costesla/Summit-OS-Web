
import os
import zipfile
import subprocess

def check_zip():
    zip_path = "test_check.zip"
    if os.path.exists(zip_path):
        os.remove(zip_path)
    
    # Run the powershell logic
    ps_cmd = '$files = Get-ChildItem -Path backend/* -Exclude ".venv", "venv", "*__pycache__*", "*.zip", ".git", ".vscode", "scripts", "*.bak", ".python_packages", "config"; Compress-Archive -Path $files -DestinationPath test_check.zip -Force'
    subprocess.run(["pwsh", "-Command", ps_cmd], check=True)
    
    print(f"Zip created at {zip_path}")
    with zipfile.ZipFile(zip_path, 'r') as z:
        names = z.namelist()
        print(f"Total files in zip: {len(names)}")
        print("\nSearching for pricing files:")
        for name in names:
            if "pricing" in name.lower():
                print(f"  MATCH: {name}")
        
        print("\nRoot level files:")
        for name in names:
            if "/" not in name and "\\" not in name:
                print(f"  ROOT: {name}")

if __name__ == "__main__":
    check_zip()
