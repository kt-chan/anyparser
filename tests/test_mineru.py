import pytest
import httpx
from app.core.config import settings
from app.services.mineru_client import MinerUClient
from app.utils.archive import compress_folder
import tarfile
from pathlib import Path
import os
import shutil

@pytest.mark.asyncio
async def test_vllm_connectivity():
    """Verify the local service can reach http://172.20.0.10:8000/v1/models"""
    endpoint = f"{settings.MINERU_VLLM_ENDPOINT}/models"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(endpoint)
            # We expect a 200 OK or at least some response from the model server
            assert response.status_code == 200
            models = response.json()
            assert "data" in models
            # Check if MinerU-2.5 is in the models list
            model_ids = [m["id"] for m in models["data"]]
            assert settings.MINERU_VLLM_MODEL_ID in model_ids
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        pytest.fail(f"VLLM Inference Server at {endpoint} is unreachable: {e}")
    except Exception as e:
        pytest.fail(f"VLLM connectivity test failed with unexpected error: {e}")

@pytest.mark.asyncio
async def test_pdf_to_markdown(sample_pdf):
    """A full integration test using a sample PDF"""
    client = MinerUClient()
    try:
        # Note: This will actually call the remote VLLM if it's reachable.
        output_dir = await client.process_pdf(sample_pdf)
        
        assert output_dir.exists()
        assert output_dir.is_dir()
        
        # Check for expected markdown file
        md_files = list(output_dir.glob("*.md"))
        assert len(md_files) > 0
        
        # Check if markdown contains "Gleason" (from our actual test.pdf content)
        content = md_files[0].read_text(encoding="utf-8")
        assert "Gleason" in content
    except Exception as e:
        pytest.fail(f"Full PDF to Markdown integration test failed: {e}")

def test_tar_creation(sample_pdf):
    """Ensure the resulting .tar contains the expected Markdown and image assets"""
    # 1. Create a mock output directory structure
    job_id = "test_tar_job"
    test_output_dir = Path(settings.TEMP_DIR) / f"output_{job_id}"
    vlm_output_dir = test_output_dir / sample_pdf.stem / "vlm"
    image_dir = vlm_output_dir / "images"
    
    image_dir.mkdir(parents=True, exist_ok=True)
    
    # 2. Create mock content
    md_file = vlm_output_dir / f"{sample_pdf.stem}.md"
    md_file.write_text("# Test Markdown", encoding="utf-8")
    
    img_file = image_dir / "test_img.png"
    img_file.write_bytes(b"mock image data")
    
    # 3. Compress
    tar_path = Path(settings.TEMP_DIR) / "test_result.tar.gz"
    compress_folder(vlm_output_dir, tar_path)
    
    # 4. Verify tar content
    assert tar_path.exists()
    assert tarfile.is_tarfile(tar_path)
    
    with tarfile.open(tar_path, "r:gz") as tar:
        names = tar.getnames()
        # The structure should be vlm/md and vlm/images/img
        # Based on arcname=folder_path.name in compress_folder
        assert "vlm" in names or f"vlm/{sample_pdf.stem}.md" in names
        # Check if it has the md file and images
        assert any(name.endswith(".md") for name in names)
        assert any("images/" in name for name in names)

    # Cleanup
    shutil.rmtree(test_output_dir)
    tar_path.unlink()
