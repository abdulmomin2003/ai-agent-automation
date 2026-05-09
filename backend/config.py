"""
Application configuration — loads from .env file.
"""

import os
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Groq & Embeddings
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIMENSIONS: int = 384

    # Supabase / Postgres
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_DB_PASSWORD: str = ""
    SUPABASE_DB_HOST: str = "aws-0-us-east-1.pooler.supabase.com"
    SUPABASE_DB_PORT: int = 6543
    SUPABASE_DB_NAME: str = "postgres"
    SUPABASE_DB_USER: str = "postgres"
    DATABASE_URL: str = ""

    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_API_SECRET_KEY: str = ""
    TWILIO_API_SID: str = ""
    TWILIO_PHONE_NUMBER: str = ""

    # ElevenLabs
    ELEVENLABS_API_KEY: str = ""

    # Email (SendGrid)
    SENDGRID_API_KEY: Optional[str] = None
    SENDGRID_FROM_EMAIL: str = "ai-agent@yourdomain.com"

    # Next.js-compatible env names
    NEXT_PUBLIC_SUPABASE_URL: str = ""
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: str = ""

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
        env_file = (
            str(Path(__file__).resolve().parents[1] / ".env"),
            ".env",
        )
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def supabase_url(self) -> str:
        return self.NEXT_PUBLIC_SUPABASE_URL or self.SUPABASE_URL

    @property
    def supabase_api_key(self) -> str:
        return (
            self.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
            or self.SUPABASE_ANON_KEY
            or self.SUPABASE_SERVICE_ROLE_KEY
        )

    @property
    def supabase_project_ref(self) -> str:
        url = self.supabase_url
        if not url:
            return ""

        hostname = urlparse(url).hostname or ""
        if hostname.endswith(".supabase.co"):
            return hostname.split(".")[0]
        return ""

    @property
    def postgres_dsn(self) -> str:
        candidates = self.postgres_dsn_candidates
        return candidates[0] if candidates else ""

    @property
    def postgres_dsn_candidates(self) -> list[str]:
        if self.DATABASE_URL:
            return [self.DATABASE_URL]

        project_ref = self.supabase_project_ref
        if not project_ref or not self.SUPABASE_DB_PASSWORD:
            return []

        from urllib.parse import quote

        password = quote(self.SUPABASE_DB_PASSWORD, safe="")
        direct_user = quote(self.SUPABASE_DB_USER, safe="")
        pool_user = quote(f"{self.SUPABASE_DB_USER}.{project_ref}", safe="")

        return [
            (
                f"postgresql://{direct_user}:{password}"
                f"@db.{project_ref}.supabase.co:5432/{self.SUPABASE_DB_NAME}"
                "?sslmode=require"
            ),
            (
                f"postgresql://{pool_user}:{password}"
                f"@{self.SUPABASE_DB_HOST}:{self.SUPABASE_DB_PORT}/{self.SUPABASE_DB_NAME}"
                "?sslmode=require"
            ),
            (
                f"postgresql://{direct_user}:{password}"
                f"@{self.SUPABASE_DB_HOST}:{self.SUPABASE_DB_PORT}/{self.SUPABASE_DB_NAME}"
                "?sslmode=require"
            ),
        ]


settings = Settings()
