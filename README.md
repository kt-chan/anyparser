# AnyParser: MinerU PDF Parser Service

AnyParser is a high-performance FastAPI wrapper for the **MinerU Python SDK**. It allows for local execution of PDF parsing with remote inference via a VLLM server, providing a scalable way to convert PDFs into high-quality Markdown and extracted assets.

## Features

- **MinerU SDK Integration**: Uses the official MinerU SDK in `vlm-http-client` mode.
- **VLM Image Enrichment**: Automatically identifies empty image tags in the generated Markdown and enriches them using a Visual Language Model (VLM).
    - **Alt-Text Generation**: Fills image brackets with descriptive 10-word technical alt-text.
    - **Contextual Description**: Appends a blockquote with a detailed technical description for RAG systems.
    - **Smart Context**: Extracts 500 characters of surrounding text to provide the VLM with document context.
- **Asynchronous Processing**: Fully async implementation with parallel image processing (Semaphore limit=5).
- **OpenAI-Compatible Backend**: Connects to VLLM Inference Servers (e.g., `MinerU-2.5`).
- **Robust Error Handling**: Includes retry logic (3 retries, 2s delay) for `429 (Rate Limit)` errors and malformed JSON parsing using `json_repair`.
- **Automatic Packaging**: Generates a `.tar.gz` archive containing enriched Markdown, images, and layout JSONs.
- **Background Cleanup**: Automatically removes temporary files and output directories after the request is completed.
- **Docker Support**: Ready-to-use Docker and Docker Compose configurations.

## Project Structure

```text
/anyparser
├── app/
│   ├── main.py              # FastAPI app initialization
│   ├── api/                 # Endpoint definitions
│   │   └── v1/
│   │       └── parse.py     # PDF upload and processing routes
│   ├── core/                # Configuration and constants
│   │   └── config.py        # Environment variable management
│   ├── services/            # Business Logic
│   │   ├── mineru_client.py # MinerU SDK integration logic
│   │   ├── vlm_client.py    # VLM API client with retry logic
│   │   └── enrichment_service.py # Markdown enrichment logic
│   └── utils/               # Helper functions (archive, file handling)
├── docker/                  # Dockerfile and docker-compose.yaml
├── logs/                    # Application and service logs
├── tests/                   # Pytest suite
├── .env                     # Local environment configuration
├── pyproject.toml           # Project setup and dependencies
└── requirements.txt         # Dependency lockfile
```

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd anyparser
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

1. **Copy the sample environment file**:
   ```bash
   cp .env-sample .env  # On Windows: copy .env-sample .env
   ```

2. **Configure your environment**:
   Edit the `.env` file and set your VLLM and Enrichment VLM endpoints:

   ```env
   # MinerU VLLM Config
   MINERU_VLLM_ENDPOINT=http://172.20.0.10:8000/v1
   MINERU_VLLM_MODEL_ID=MinerU-2.5

   # Enrichment VLM Config
   VLM_HOST_PATH=http://172.20.0.10:8000/v1
   VLM_MODEL_NAME=MinerU-2.5
   VLM_API_KEY=your_api_key_here

   TEMP_DIR=temp
   LOGS_DIR=logs
   ```

## Running the Service

### Using Docker (Recommended)
Build and start the service using Docker Compose:
```bash
docker-compose -f docker/docker-compose.yaml up --build
```

### Local Execution
Run the service using `uvicorn`:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```
The service will be available at `http://localhost:8080`.

## API Usage

### Parse PDF
**POST** `/v1/pdf/parse`

Accepts a binary PDF file. The service will:
1. Parse the PDF using MinerU.
2. Enrich the generated Markdown images using the VLM.
3. Return a `.tar.gz` archive of the results.

**Example with curl**:
```bash
curl -X POST http://localhost:8080/v1/pdf/parse \
  -F "file=@/path/to/your/document.pdf" \
  --output results.tar.gz
```

### System Cleanup
**POST** `/v1/system/cleanup`

Manually triggers a cleanup of the entire `temp/` directory.

### Health Check
**GET** `/health`

## Testing

Run the enrichment-specific tests:
```bash
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe -m pytest tests/test_enrichment.py
```

Run the full test suite:
```bash
pytest
```

## License

[Internal/Private] - See repository owner for details.
