import os
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Remote Backend Config
    REMOTE_HOST: str = Field("172.20.0.10", description="Remote host address")
    REMOTE_PORT: int = Field(22, description="SSH port")
    REMOTE_USER: str = Field("root", description="Remote username")
    REMOTE_KEY_PATH: str = Field("keys/id_rsa", description="Path to SSH private key")
    REMOTE_MINERU_DIR: str = Field(
        "/home/demo/docker/mineru", description="Remote MinerU directory"
    )

    # VLLM Config
    MINERU_VLLM_ENDPOINT: str = Field(
        "http://172.20.0.10:8000/v1", description="VLLM endpoint for MinerU"
    )
    MINERU_VLLM_MODEL_ID: str = Field(
        "MinerU-2.5", description="Model ID for MinerU VLLM"
    )

    # Enrichment VLM Config
    VLM_HOST_PATH: str = Field(
        "http://172.20.0.10:8000/v1", description="VLM host path"
    )
    VLM_MODEL_NAME: str = Field("MinerU-2.5", description="VLM model name")
    VLM_API_KEY: str = Field("EMPTY", description="API key for VLM")

    # Enrichment LLM Config
    LLM_HOST_PATH: str = Field(
        "http://172.20.0.10:8000/v1", description="LLM host path"
    )
    LLM_MODEL_NAME: str = Field("Qwen2.5-7B-Instruct", description="LLM model name")
    LLM_API_KEY: str = Field("EMPTY", description="API key for LLM")
    ENABLE_LLM_SUMMARIZATION: bool = Field(
        False, description="Enable LLM summarization feature"
    )

    # MinerU SDK Env Vars (can be overridden in .env)
    MINERU_VL_MODEL_NAME: str | None = Field(
        None, description="Optional override for MinerU VL model name"
    )
    MINERU_VL_SERVER: str | None = Field(
        None, description="Optional override for MinerU VL server endpoint"
    )

    # Local Config
    HOST: str = Field("127.0.0.1", description="Local host to bind")
    PORT: int = Field(8080, description="Local port to bind")
    TEMP_DIR: str = Field("temp", description="Temporary directory")
    LOGS_DIR: str = Field("logs", description="Logs directory")
    LOG_LEVEL: str = Field("INFO", description="Global log level (DEBUG, INFO, ERROR)")
    ENABLE_DAILY_CLEANUP: bool = Field(True, description="Enable daily temp cleanup")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @model_validator(mode="after")
    def setup_mineru_env(self) -> "Settings":
        """
        Ensure MinerU environment variables are set for the SDK.
        Runs after all field values are loaded.
        """
        if not os.environ.get("MINERU_VL_MODEL_NAME"):
            os.environ["MINERU_VL_MODEL_NAME"] = (
                self.MINERU_VL_MODEL_NAME or self.MINERU_VLLM_MODEL_ID
            )
        if not os.environ.get("MINERU_VL_SERVER"):
            os.environ["MINERU_VL_SERVER"] = (
                self.MINERU_VL_SERVER or self.MINERU_VLLM_ENDPOINT
            )
        return self


settings = Settings()
