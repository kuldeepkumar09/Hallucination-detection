"""
Settings loaded from environment variables / .env file.
All thresholds, model choices, and feature flags are configurable at runtime.
New features are opt-in via boolean flags — defaults preserve original behaviour.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- LLM provider: "ollama" (free/local) or "anthropic" (paid) ----
    llm_provider: str = "ollama"

    # ---- Ollama (free local LLM) ----
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_api_key: str = "ollama"  # Ollama ignores this but OpenAI client requires it

    # ---- Anthropic API (optional, only needed if llm_provider=anthropic) ----
    anthropic_api_key: str = ""
    anthropic_api_base: str = "https://api.anthropic.com"

    # ---- Proxy server ----
    proxy_host: str = "0.0.0.0"
    proxy_port: int = 8080

    # ---- Detection models ----
    extractor_model: str = "llama3.2"   # Ollama model name
    verifier_model: str = "llama3.2"    # Ollama model name

    # ---- Decision thresholds ----
    block_threshold: float = 0.25
    flag_threshold: float = 0.60

    # ---- Knowledge base (ChromaDB) ----
    kb_persist_dir: str = "./chroma_db"
    kb_collection_name: str = "authoritative_docs"
    kb_top_k: int = 3
    kb_min_relevance: float = 0.35

    # ---- KB chunking (now configurable) ----
    kb_chunk_size: int = 512
    kb_chunk_overlap: int = 64

    # ---- Extraction ----
    max_claims_per_response: int = 8

    # ---- Annotation ----
    annotate_verified: bool = True

    # ---- Hybrid search (BM25 + vector) ----
    bm25_enabled: bool = True
    bm25_weight: float = 0.40        # BM25 share; vector gets (1 - bm25_weight)

    # ---- Multi-query / HyDE retrieval ----
    hyde_enabled: bool = False        # Generate a hypothetical doc before querying
    multi_query_enabled: bool = True  # Generate N query variants per claim
    multi_query_count: int = 2

    # ---- Cross-encoder re-ranking ----
    reranker_enabled: bool = False
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranker_top_k: int = 3           # Keep top-k after re-ranking

    # ---- Verification cache ----
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600
    redis_url: str = ""               # Empty → use in-memory fallback

    # ---- Ensemble (multi-model) verification ----
    ensemble_for_critical: bool = False
    ensemble_model: str = "llama3.2"  # Second model for ensemble (can be same or larger)

    # ---- Runtime ----
    max_workers: int = 4
    request_timeout: float = 480.0
    log_level: str = "INFO"

    # ---- Audit ----
    audit_log_path: str = "./audit_trail.jsonl"


@lru_cache
def get_settings() -> Settings:
    return Settings()
