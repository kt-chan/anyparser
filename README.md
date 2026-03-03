# AnyParser: MinerU PDF Parser Service

AnyParser is a high-performance FastAPI wrapper for the **MinerU Python SDK**. it allows for local execution of PDF parsing with remote inference via a VLLM server, providing a scalable way to convert PDFs into high-quality Markdown and extracted assets.

## Features

- **MinerU SDK Integration**: Uses the official MinerU SDK in `vlm-http-client` mode.
- **Asynchronous Processing**: Fully async implementation compatible with FastAPI's event loop.
- **OpenAI-Compatible Backend**: Connects to VLLM Inference Servers (e.g., `MinerU-2.5`).
- **Automatic Packaging**: Generates a `.tar.gz` archive containing Markdown, images, and layout JSONs.
- **Background Cleanup**: Automatically removes temporary files and output directories after the request is completed.
- **Modern Config**: Managed via Pydantic Settings and `.env` files.

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
│   │   └── mineru_client.py # MinerU SDK integration logic
│   └── utils/               # Helper functions (archive, file handling)
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
   Edit the `.env` file and set your VLLM endpoint and other configuration options:

   ```env
   VLLM_ENDPOINT=http://172.20.0.10:8000/v1
   VLLM_MODEL_ID=MinerU-2.5
   TEMP_DIR=temp
   LOGS_DIR=logs
   ```

## Running the Service

You can run the service using `uvicorn` or directly via Python:

```bash
# Using uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

# Or directly
python app/main.py
```

The service will be available at `http://localhost:8080`.

## API Usage

### Parse PDF
**POST** `/v1/pdf/parse`

Accepts a binary PDF file and returns a `.tar.gz` archive of the results.

**Example with curl**:
```bash
curl -X POST http://localhost:8080/v1/pdf/parse 
  -F "file=@/path/to/your/document.pdf" 
  --output results.tar.gz
```

### System Cleanup
**POST** `/v1/system/cleanup`

Manually triggers a cleanup of the entire `temp/` directory.

**Example with curl**:
```bash
curl -X POST http://localhost:8080/v1/system/cleanup
```

### Health Check
**GET** `/health`

Returns the status of the service.

## Automatic Cleanup

- **Job Cleanup**: Each parsing job's temporary files are cleaned up via a background task immediately after the response is sent.
- **Daily Maintenance**: A background task runs every 24 hours to ensure the `temp/` directory remains clean from any orphaned files.
## Testing

Run the full test suite using `pytest`:

```bash
pytest
```

The tests cover:
- VLLM server connectivity.
- End-to-end PDF to Markdown integration.
- Archive creation and file utility logic.
- API endpoint validation.

## License

[Internal/Private] - See repository owner for details.
