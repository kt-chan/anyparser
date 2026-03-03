import pytest
import shutil
import tarfile
from pathlib import Path
from app.utils.archive import compress_folder
from app.utils.file_handler import cleanup_file
from app.core.config import settings

def test_compress_folder(tmp_path):
    # Setup: Create a dummy folder with a file
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()
    test_file = test_dir / "hello.txt"
    test_file.write_text("world")
    
    output_tar = tmp_path / "test.tar.gz"
    
    # Act
    compress_folder(test_dir, output_tar)
    
    # Assert
    assert output_tar.exists()
    assert tarfile.is_tarfile(output_tar)
    
    with tarfile.open(output_tar, "r:gz") as tar:
        names = tar.getnames()
        # Depending on arcname, it might be "test_dir/hello.txt" or just "hello.txt"
        # Our implementation uses arcname=folder_path.name, so "test_dir/hello.txt"
        assert any("hello.txt" in name for name in names)

def test_cleanup_file(tmp_path):
    # Setup
    test_file = tmp_path / "cleanup_me.txt"
    test_file.write_text("delete me")
    
    # Act
    cleanup_file(test_file)
    
    # Assert
    assert not test_file.exists()

def test_cleanup_file_not_exists():
    # Setup
    non_existent = Path("non_existent_file.txt")
    
    # Act & Assert (should not raise exception)
    cleanup_file(non_existent)
