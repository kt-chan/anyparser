import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Remote Backend Config
    REMOTE_HOST: str = "172.20.0.10"
    REMOTE_PORT: int = 22
    REMOTE_USER: str = "root"
    REMOTE_KEY_PATH: str = "keys/id_rsa"
    REMOTE_MINERU_DIR: str = "/home/demo/docker/mineru"
    
    # VLLM Config
    MINERU_VLLM_ENDPOINT: str = "http://172.20.0.10:8000/v1"
    MINERU_VLLM_MODEL_ID: str = "MinerU-2.5"
    
    # Enrichment VLM Config
    VLM_HOST_PATH: str = "http://172.20.0.10:8000/v1"
    VLM_MODEL_NAME: str = "MinerU-2.5"
    VLM_API_KEY: str = "EMPTY"
    
    # Enrichment LLM Config
    LLM_HOST_PATH: str = "http://172.20.0.10:8000/v1"
    LLM_MODEL_NAME: str = "Qwen2.5-7B-Instruct"
    LLM_API_KEY: str = "EMPTY"
    ENABLE_LLM_SUMMARIZATION: bool = False
    
    # MinerU SDK Env Vars (can be overridden in .env)
    MINERU_VL_MODEL_NAME: str | None = None
    MINERU_VL_SERVER: str | None = None

    def setup_mineru_env(self):
        """ ensure MinerU environment variables are set for the SDK """
        import os
        if not os.environ.get("MINERU_VL_MODEL_NAME"):
            os.environ["MINERU_VL_MODEL_NAME"] = self.MINERU_VL_MODEL_NAME or self.MINERU_VLLM_MODEL_ID
        if not os.environ.get("MINERU_VL_SERVER"):
            os.environ["MINERU_VL_SERVER"] = self.MINERU_VL_SERVER or self.MINERU_VLLM_ENDPOINT

    # Local Config
    TEMP_DIR: str = "temp"
    LOGS_DIR: str = "logs"
    ENABLE_DAILY_CLEANUP: bool = True
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
