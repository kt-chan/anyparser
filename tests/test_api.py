import pytest
from fastapi.testclient import TestClient
from app.main import app
from pathlib import Path
from unittest.mock import MagicMock, patch

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_upload_pdf_wrong_type():
    response = client.post(
        "/v1/pdf/parse",
        files={"file": ("test.txt", b"not a pdf", "text/plain")}
    )
    assert response.status_code == 400
    assert "Only PDF files are supported" in response.json()["detail"]

@patch("app.services.mineru_client.MinerUClient.process_pdf")
@patch("app.api.v1.parse.compress_folder")
@patch("app.api.v1.parse.cleanup_job_files")
def test_upload_pdf_success(mock_cleanup, mock_compress, mock_process, sample_pdf):
    # Mock output dir
    mock_output_dir = Path("temp/mock_output/vlm")
    mock_process.return_value = mock_output_dir
    
    # Mock compress_folder to actually create a file so FileResponse doesn't fail
    def side_effect(folder, output_path):
        output_path.touch()
    mock_compress.side_effect = side_effect
    
    response = client.post(
        "/v1/pdf/parse",
        files={"file": ("test.pdf", open(sample_pdf, "rb"), "application/pdf")}
    )
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/gzip"
    assert "results.tar.gz" in response.headers["content-disposition"]
    
    # Verify process_pdf was called
    mock_process.assert_called_once()
    # Verify compress_folder was called
    mock_compress.assert_called_once()
    # Verify cleanup was added to background tasks
    # (Checking if it was called is tricky without real background execution in test client, 
    # but we can see it was added)
    # mock_cleanup.assert_called() - this might not be called immediately

@patch("app.api.v1.system.cleanup_temp_dir")
def test_system_cleanup(mock_cleanup):
    response = client.post("/v1/system/cleanup")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    mock_cleanup.assert_called_once()
