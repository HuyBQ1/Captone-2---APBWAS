from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'postgresql+psycopg://apbwas:apbwas@localhost:5432/apbwas'
    agent_database_url: str = ''
    redis_url: str = 'redis://localhost:6379/0'
    demo_mode: bool = True
    provider: str = 'openai'
    ai_model: str = 'gpt-4o-mini'
    embedding_model: str = 'text-embedding-3-small'
    openai_api_key: str = ''
    gemini_api_key: str = ''
    cookie_secure: bool = False
    frontend_origin: str = 'http://127.0.0.1:5173'
    session_hours: int = 12
    upload_dir: str = 'uploads'
    audit_key: str = 'demo-audit-key-change-in-connected-mode'
    demo_password: str = 'Demo@123456'

settings = Settings()
