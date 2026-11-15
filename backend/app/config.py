from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, Field, field_validator
from urllib.parse import urlsplit

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'postgresql+psycopg://apbwas:apbwas@localhost:5432/apbwas'
    agent_database_url: str = ''
    redis_url: str = 'redis://localhost:6379/0'
    demo_mode: bool = True
    provider: str = 'openai'
    ai_model: str = 'gpt-4o-mini'
    agent_models: str = ''
    ai_base_url: str = ''
    ai_api_key: SecretStr = SecretStr('')
    ai_provider_label: str = ''
    ai_json_mode: bool = True
    ai_timeout_seconds: int = Field(default=45,ge=5,le=120)
    sample_data: bool = False
    embedding_provider: str = ''
    embedding_model: str = 'text-embedding-3-small'
    openai_api_key: str = ''
    gemini_api_key: str = ''
    cookie_secure: bool = False
    frontend_origin: str = 'http://127.0.0.1:5173'
    session_hours: int = 12
    upload_dir: str = 'uploads'
    audit_key: str = 'demo-audit-key-change-in-connected-mode'
    demo_password: str = 'Demo@123456'
    gmail_sender: str = ''
    gmail_client_id: str = ''
    gmail_client_secret: SecretStr = SecretStr('')
    gmail_redirect_uri: str = ''
    mail_encryption_key: SecretStr = SecretStr('')
    llm_encryption_key: SecretStr = SecretStr('')
    mail_bulk_daily_limit: int = Field(default=100,ge=1,le=500)

    @field_validator('ai_base_url')
    @classmethod
    def validate_ai_base_url(cls,value):
        if not value:return value
        parsed=urlsplit(value)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('AI_BASE_URL phải là HTTPS base URL, không kèm thông tin đăng nhập, query hoặc fragment.')
        return value.rstrip('/')

settings = Settings()
