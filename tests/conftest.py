import pytest
from app.core.config import settings
from pathlib import Path

@pytest.fixture
def sample_pdf():
    pdf_path = Path("tests/test.pdf")
    if not pdf_path.exists():
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(str(pdf_path))
        c.drawString(100, 750, "Hello World - MinerU Test")
        c.save()
    return pdf_path

@pytest.fixture
def vllm_endpoint():
    return settings.VLLM_ENDPOINT
