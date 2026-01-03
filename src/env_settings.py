from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvironmentSettings(BaseSettings):
    GOOGLE_API_KEY: str
    LLAMA_CLOUD_API_KEY: str

    ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    DATABASE_URI: str
    DATABASE_NAME: str
    REDIS_URI: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @classmethod
    def load(cls) -> "EnvironmentSettings":
        return cls()  # type: ignore
