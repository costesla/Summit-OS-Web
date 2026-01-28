import os
import zipfile
import sys

def zip_backend():
    output_filename = 'deploy_backend.zip'
    backend_dir = 'backend'
    
    print(f"Zipping {backend_dir} to {output_filename}")
    sys.stdout.flush()
    
    with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(backend_dir):
            dirs[:] = [d for d in dirs if d not in ['.venv', 'venv', '__pycache__', '.git', '.vscode', '.python_packages']]
            
            for file in files:
                if file.endswith('.pyc'): continue
                
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, start=backend_dir)
                # print(f"Adding {arcname}")
                zipf.write(file_path, arcname)
    
    if os.path.exists(output_filename):
        print(f"SUCCESS: {output_filename} exists. Size: {os.path.getsize(output_filename)}")
    else:
        print(f"FAILURE: {output_filename} was not created.")

if __name__ == '__main__':
    zip_backend()
