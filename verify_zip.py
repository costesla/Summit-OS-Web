
import zipfile
import os

def verify_zip(zip_path):
    print(f"Verifying {zip_path}...")
    if not os.path.exists(zip_path):
        print("ERROR: Zip file not found!")
        return
        
    with zipfile.ZipFile(zip_path, 'r') as z:
        names = z.namelist()
        print(f"Total files: {len(names)}")
        
        # Check critical files
        critical = ['function_app.py', 'host.json', 'api/pricing.py', 'services/pricing.py', 'requirements.txt']
        for c in critical:
            found = c in names or c.replace('/', '\\') in names
            print(f"  {c}: {'FOUND' if found else 'MISSING'}")
            if found:
                # Print the actual name found (check for slashes)
                actual = [n for n in names if n == c or n == c.replace('/', '\\')][0]
                print(f"    (Internal path: {actual})")

if __name__ == "__main__":
    verify_zip("backend_deploy.zip")
