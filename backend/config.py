"""
Application configuration — loads from .env file.
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenAI
    OPENAI_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    LLM_MODEL: str = "gpt-4o-mini"
    EMBEDDING_DIMENSIONS: int = 1536

    # Chunking
    CHUNK_SIZE: int = 512          # tokens
    CHUNK_OVERLAP: int = 50        # tokens (~10%)

    # Retrieval
    TOP_K_RETRIEVAL: int = 10      # initial retrieval count
    TOP_K_RERANK: int = 5          # after reranking
    BM25_WEIGHT: float = 0.3      # weight for BM25 in hybrid fusion
    SEMANTIC_WEIGHT: float = 0.7  # weight for semantic in hybrid fusion

    # Reranker
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Vector Store (FAISS)
    VECTOR_STORE_DIR: str = "./vector_db"

    # Upload
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE_MB: int = 50

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
