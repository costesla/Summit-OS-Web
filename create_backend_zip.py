import os
import zipfile

def zip_backend(output_filename):
    backend_dir = 'backend'
    with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(backend_dir):
            # Exclude directories
            dirs[:] = [d for d in dirs if d not in ['.venv', 'venv', 'venv32', '__pycache__', '.git', '.vscode', '.python_packages']]
            
            for file in files:
                if file.endswith('.pyc') or file == output_filename:
                    continue
                
                file_path = os.path.join(root, file)
                # Arcname should be relative to backend/ so that function_app.py is at execution root if required,
                # BUT for Azure Functions in a subfolder, often we want the files at the root of the zip.
                # If we deploy to standard Azure Functions, it expects host.json at the root of the zip.
                # So we must strip 'backend/' from the path.
                
                arcname = os.path.relpath(file_path, start=backend_dir)
                # FORCE forward slashes for Linux compatibility
                arcname = arcname.replace(os.sep, '/')
                print(f"Adding {arcname}")
                zipf.write(file_path, arcname)

if __name__ == '__main__':
    zip_backend('backend_deploy.zip')
    print("Zip created: backend_deploy.zip")
