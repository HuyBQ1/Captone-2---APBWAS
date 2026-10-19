from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from contextlib import contextmanager
from sqlalchemy import text
from .config import settings
from datetime import timezone
from sqlalchemy.types import TypeDecorator, DateTime

class UTCDateTime(TypeDecorator):
    impl=DateTime(timezone=True)
    cache_ok=True
    def process_bind_param(self,value,dialect):
        if value is None:return None
        value=value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return value.replace(tzinfo=None) if dialect.name=='sqlite' else value
    def process_result_value(self,value,dialect):
        if value is None:return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

class Base(DeclarativeBase):
    pass

engine = create_engine(settings.database_url, pool_pre_ping=True,
                       connect_args={'check_same_thread': False} if settings.database_url.startswith('sqlite') else {})
Session = sessionmaker(engine, expire_on_commit=False)
read_engine=create_engine(settings.agent_database_url,pool_pre_ping=True) if settings.agent_database_url else engine

@contextmanager
def read_only_db(db):
    if db.bind.dialect.name!='postgresql':
        # Test harness: SQL surface is still structured SELECT only.
        yield db
        return
    with sessionmaker(read_engine)() as reader:
        reader.execute(text('SET TRANSACTION READ ONLY'))
        reader.execute(text("SET LOCAL statement_timeout = '2500ms'"))
        try:
            yield reader
        finally:
            reader.rollback()

def get_db():
    with Session() as db:
        yield db
