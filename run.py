"""Sobe o servidor local. Uso: python run.py"""
import uvicorn

from app.config import settings

if __name__ == "__main__":
    print(f"\n  Campanhas SHILD — abra:  http://{settings.host}:{settings.port}\n")
    uvicorn.run("app.server:app", host=settings.host, port=settings.port, reload=False)
