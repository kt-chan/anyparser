import os
import uuid
from pathlib import Path
from app.core.config import settings
from loguru import logger
from mineru.cli.common import aio_do_parse, read_fn

class MinerUClient:
    def __init__(self):
        self.MINERU_VLLM_ENDPOINT = settings.MINERU_VLLM_ENDPOINT
        self.temp_dir = Path(settings.TEMP_DIR)
        self.temp_dir.mkdir(exist_ok=True)

    async def process_pdf(self, local_pdf_path: Path) -> Path:
        """
        Parses a PDF using the MinerU Python SDK in vlm-http-client mode (Asynchronous).
        """
        job_id = str(uuid.uuid4())
        output_dir = self.temp_dir / f"output_{job_id}"
        output_dir.mkdir(exist_ok=True)
        
        pdf_name = local_pdf_path.stem
        
        try:
            logger.info(f"Starting Async MinerU SDK job {job_id} for {local_pdf_path}")
            
            # Read PDF bytes using MinerU's helper
            pdf_bytes = read_fn(local_pdf_path)
            
            # Invoke MinerU SDK Asynchronously
            await aio_do_parse(
                output_dir=str(output_dir),
                pdf_file_names=[pdf_name],
                pdf_bytes_list=[pdf_bytes],
                p_lang_list=["ch","en"], 
                backend="vlm-http-client",
                server_url=self.MINERU_VLLM_ENDPOINT,
                f_draw_layout_bbox=True,
                f_draw_span_bbox=True,
                f_dump_md=True,
                f_dump_middle_json=False,
                f_dump_model_output=False,
                f_dump_orig_pdf=True,
                f_dump_content_list=True
            )
            
            # The output will be in output_dir / pdf_name / vlm
            actual_output_path = output_dir / pdf_name / "vlm"
            if not actual_output_path.exists():
                # Fallback check if it used another path structure
                logger.warning(f"Expected output path {actual_output_path} not found. Searching in {output_dir}")
                # Sometimes it might be directly in output_dir or under a different parse_method name
                for p in output_dir.rglob("*.md"):
                    actual_output_path = p.parent
                    break
            
            return actual_output_path

        except Exception as e:
            logger.error(f"Failed to process PDF {local_pdf_path} with SDK: {e}")
            raise e

# For compatibility with existing code
class MinerUWrapper(MinerUClient):
    pass
