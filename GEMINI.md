# Project Context: FastAPI Semantic Chunker

You are an expert Backend Architect. This project is a FastAPI-based service for processing high-fidelity documents such as PDF, Markdown, Office, Text data into semantic chunks for RAG pipelines.

## 🛠 Environment Specification
- **Framework**: FastAPI (Python 3.10+)
- **Scope**: You have access to the project root. Refer to `.geminiignore` to see which directories are excluded from your scan.
- **Dependencies**: Use `pydantic` for data schemas and `mistletoe` or `marko` for Markdown AST parsing.

## 📏 Coding Practice Guide

### 1. FastAPI Standards
- **Pydantic Models**: All request/response bodies must use Pydantic `BaseModel`.
- **Async First**: Use `async def` for endpoints.
- **Error Handling**: Use `HTTPException` with descriptive status codes.
- **Dependency Injection**: Use `Depends` for reusable components like the Chunker class.
- **Package Management**: "When adding new features, always check if new dependencies are required. If so, remind the user to update the root requirements.txt and provide the exact pip install command."

### 2. Environment and Constrains
* VLM Endpoint:  scan environment variables (VLM_HOST_PATH, VLM_MODEL_NAME, and VLM_API_KEY) in project root directory .env files.
* LLM Endpoint:  scan environment variables (LLM_HOST_PATH, LLM_MODEL_NAME, and LLM_API_KEY) in project root directory .env files.
* Local Env: Windows (PowerShell), Python 3.10+, python interpreter at @.venv\Scripts\python.exe

### 3. Project Structure (Modular): 
Implement the project using this strict directory hierarchy to ensure maintainability:
/anyparser
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app initialization & exception handlers
│   ├── api/                 # Endpoint definitions
│   │   └── v1/
│   │       └── parse.py     # OpenAI-compatible PDF upload routes
│   ├── core/                # Configuration and global constants
│   │   └── config.py        # SSH paths, VLLM endpoints, & Env vars
│   ├── services/            # Business Logic (The "Brain")
│   │   ├── mineru_client.py # MinerU SDK integration & VLM-HTTP logic
│   │   └── ssh_manager.py   # Paramiko wrapper for remote host commands
│   └── utils/               # Helper functions
│       ├── archive.py       # Tar/Zip compression logic
│       └── file_handler.py  # Local temp file management
├── keys/
│   └── id_rsa               # SSH Private Key (Mount/Copy here)
├── logs/                    # Application and SDK log files
├── tests/                   # Pytest suite
│   ├── conftest.py          # Shared fixtures (e.g., mock SSH)
│   ├── test_api.py          # Endpoint integration tests
│   └── test_mineru.py       # Logic unit tests
├── temp/                    # Workspace for PDF processing
├── pyproject.toml           # Modern dependency management (uv)
└── Dockerfile               # Client-side deployment
