"""Explicit local verification harness. Production Compose always uses PostgreSQL."""
import os, subprocess, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
os.chdir(root/'backend')
os.environ['DATABASE_URL']='sqlite:///'+str(root/'local-demo-v1.db').replace('\\','/')
os.environ['DEMO_MODE']='true'
os.environ['REDIS_URL']='redis://127.0.0.1:6399/0'
os.environ['UPLOAD_DIR']=str(root/'uploads')
sys.path.insert(0,str(root/'backend'))
from app.db import Base,engine
from app.seed import seed
from alembic import command
from alembic.config import Config
command.upgrade(Config('alembic.ini'),'head')
seed()
worker=subprocess.Popen([sys.executable,'-m','app.worker'],env=os.environ.copy())
try:
    subprocess.run([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000'],check=True)
finally:
    worker.terminate()
    worker.wait(timeout=10)
