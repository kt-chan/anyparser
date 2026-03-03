import os
import tarfile
from pathlib import Path
from loguru import logger

def compress_folder(folder_path, output_path):
    """
    Compresses a folder into a .tar.gz archive.
    """
    folder_path = Path(folder_path)
    output_path = Path(output_path)
    
    logger.info(f"Compressing {folder_path} to {output_path}")
    try:
        with tarfile.open(output_path, "w:gz") as tar:
            tar.add(folder_path, arcname=folder_path.name)
        return output_path
    except Exception as e:
        logger.error(f"Failed to compress {folder_path}: {e}")
        raise e
