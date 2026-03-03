import os
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile
from app.core.config import settings

def save_upload_file(upload_file):
    """
    Saves an uploaded file to a temporary location.
    """
    temp_dir = Path(settings.TEMP_DIR)
    temp_dir.mkdir(exist_ok=True)
    
    with NamedTemporaryFile(delete=False, suffix=".pdf", dir=temp_dir) as temp_file:
        shutil.copyfileobj(upload_file.file, temp_file)
        return Path(temp_file.name)

def cleanup_file(file_path):
    """
    Deletes a file if it exists.
    """
    file_path = Path(file_path)
    if file_path.exists():
        file_path.unlink()

def cleanup_directory(dir_path):
    """
    Deletes a directory and its contents.
    """
    dir_path = Path(dir_path)
    if dir_path.exists() and dir_path.is_dir():
        shutil.rmtree(dir_path)

def cleanup_temp_dir():
    """
    Cleans up the entire TEMP_DIR.
    """
    temp_dir = Path(settings.TEMP_DIR)
    if temp_dir.exists():
        for item in temp_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    return True
