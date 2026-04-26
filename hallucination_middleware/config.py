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

    # ---- LLM provider: "ollama" | "anthropic" | "nvidia_nim" ----
    llm_provider: str = "ollama"

    # ---- Ollama (free local LLM) ----
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_api_key: str = "ollama"  # Ollama ignores this but OpenAI client requires it
    ollama_num_parallel: int = 1
    ollama_max_loaded_models: int = 1
    ollama_num_ctx: int = 4096

    # ---- Anthropic API (optional, only needed if llm_provider=anthropic) ----
    anthropic_api_key: str = ""
    anthropic_api_base: str = "https://api.anthropic.com"

    # ---- Web search ----
    tavily_api_key: str = ""

    # ---- NVIDIA NIM (OpenAI-compatible, free tier at build.nvidia.com) ----
    nvidia_nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_nim_api_key: str = ""

    # ---- Together AI (automatic fallback when Anthropic hits rate limits) ----
    together_api_key: str = ""
    together_base_url: str = "https://api.together.xyz/v1"
    together_extractor_model: str = "meta-llama/Llama-3.1-8B-Instruct-Turbo"
    together_verifier_model: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    fallback_enabled: bool = True

    # ---- Proxy server ----
    proxy_host: str = "0.0.0.0"
    proxy_port: int = 8080

    # ---- Detection models ----
    extractor_model: str = "phi3:mini"   # Ollama model name
    verifier_model: str = "phi3:mini"    # Ollama model name

    # ---- Decision thresholds (global fallback) ----
    block_threshold: float = 0.50
    flag_threshold: float = 0.60

    # ---- Domain-specific thresholds (calibrated for Claude Haiku/Sonnet) ----
    # Claude outputs well-calibrated confidence 0.70-0.95 for correct facts.
    # Keys: MEDICAL | LEGAL | FINANCIAL | GENERAL
    domain_block_thresholds: dict = {
        "MEDICAL": 0.65, "LEGAL": 0.60, "FINANCIAL": 0.58, "GENERAL": 0.40
    }
    domain_flag_thresholds: dict = {
        "MEDICAL": 0.75, "LEGAL": 0.70, "FINANCIAL": 0.65, "GENERAL": 0.55
    }

    # ---- Knowledge base (ChromaDB) ----
    kb_persist_dir: str = "./chroma_db"
    kb_collection_name: str = "authoritative_docs"
    kb_top_k: int = 5          # Increased from 3 — more candidates → fewer unverifiable
    kb_min_relevance: float = 0.28  # Lowered from 0.35 — cast wider net on retrieval

    # ---- KB chunking (now configurable) ----
    kb_chunk_size: int = 512
    kb_chunk_overlap: int = 64

    # ---- Extraction ----
    max_claims_per_response: int = 25

    # ---- Annotation ----
    annotate_verified: bool = True

    # ---- Hybrid search (BM25 + vector) ----
    bm25_enabled: bool = True
    bm25_weight: float = 0.35        # BM25 share; vector gets (1 - bm25_weight)

    # ---- Multi-query / HyDE retrieval ----
    hyde_enabled: bool = True         # Generate a hypothetical doc before querying (bridges phrasing gap)
    multi_query_enabled: bool = True  # Generate N query variants per claim
    multi_query_count: int = 1

    # ---- Cross-encoder re-ranking ----
    reranker_enabled: bool = True
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranker_top_k: int = 3           # Keep top-k after re-ranking
    reranker_candidate_count: int = 10  # Retrieve this many docs before reranking

    # ---- Verification cache ----
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600
    redis_url: str = "redis://localhost:6379"  # Override in docker-compose with redis://redis:6379
    # Disk-cache encryption (optional). Generate key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    cache_encryption_key: str = ""            # Leave empty to disable encryption

    # ---- Semantic cache ----
    semantic_cache_enabled: bool = True
    semantic_cache_threshold: float = 0.85  # Cosine similarity threshold
    chroma_db_path: str = "./chroma_db"

    # ---- Ensemble (multi-model) verification ----
    ensemble_for_critical: bool = False
    ensemble_model: str = "claude-sonnet-4-6"  # Different from extractor for true diversity

    # ---- Self-correction loop ----
    self_correction_enabled: bool = True   # Rewrite flagged/blocked text using evidence

    # ---- MPC (Model Predictive Control) — receding horizon verification ----
    mpc_enabled: bool = False              # Off by default (expensive — adds N*3 LLM calls)
    mpc_candidates: int = 3               # Number of candidate alternatives per chunk
    mpc_max_sentences: int = 10           # Hard cap on sentences processed (cost guard)

    # ---- Web-RAG fallback ----
    web_rag_enabled: bool = True           # Fall back to live web search when KB score is low
    web_rag_kb_threshold: float = 0.25    # KB relevance below this triggers web search

    # ---- Wikipedia auto-seed ----
    wiki_auto_seed_enabled: bool = True    # Seed KB with starter Wikipedia articles on startup
    wiki_auto_seed_threshold: int = 5000  # Seed until KB has at least this many chunks
    wiki_auto_seed_topics: str = (         # Comma-separated topics (overridable in .env)
        # Science & Medicine
        "Albert Einstein,DNA,Vaccination,COVID-19 pandemic,Diabetes mellitus,"
        "Penicillin,Cancer,Human brain,Evolution,Quantum mechanics,"
        "Climate change,Photosynthesis,Black hole,CRISPR,Antibiotic resistance,"
        # History & Politics
        "World War II,World War I,French Revolution,Cold War,United Nations,"
        "American Revolution,Russian Revolution,Holocaust,Civil rights movement,"
        # Technology
        "Artificial intelligence,Internet,Python (programming language),"
        "Blockchain,Machine learning,Semiconductor,Space exploration,Nuclear power,"
        # Economics & Finance
        "Inflation,Stock market,Gross domestic product,Federal Reserve,"
        "Cryptocurrency,Great Depression,Supply chain,Free trade,"
        # Law & Society
        "United States Constitution,Human rights,Democracy,Feminism,"
        "International law,Geneva Convention,Universal Declaration of Human Rights,"
        # Geography & Culture
        "Amazon rainforest,Himalayas,Mediterranean Sea,Silk Road"
    )

    @property
    def wiki_seed_topics_list(self) -> list:
        return [t.strip() for t in self.wiki_auto_seed_topics.split(",") if t.strip()]

    # ---- Runtime ----
    max_workers: int = 4
    request_timeout: float = 120.0
    log_level: str = "INFO"

    # ---- Streaming verification ----
    streaming_enabled: bool = True          # Enable claim-by-claim streaming
    streaming_claim_delay: float = 0.05    # Near-real-time per-claim updates
    streaming_batch_size: int = 1          # One claim at a time for true live streaming

    # ---- Security ----
    # api_key: comma-separated read+verify keys (can call /verify, /audit, /kb/stats, /health)
    # admin_key: comma-separated admin-only keys (additionally: /kb/ingest, /kb/delete, /cache/clear)
    api_key: str = ""
    admin_key: str = ""
    rate_limit_enabled: bool = True   # 20 req/min per IP
    rate_limit_requests: int = 20     # max requests per window
    rate_limit_window: int = 60       # window size in seconds
    # Redis-backed rate limiting (uses same redis_url as cache)
    rate_limit_redis_enabled: bool = True

    @property
    def valid_api_keys(self) -> set:
        return {k.strip() for k in self.api_key.split(",") if k.strip()}

    @property
    def valid_admin_keys(self) -> set:
        return {k.strip() for k in self.admin_key.split(",") if k.strip()}
    # Comma-separated list — pydantic_settings cannot parse Python list literals from .env
    allowed_origins: str = "http://localhost:5173,http://localhost:8080,http://127.0.0.1:5173,http://127.0.0.1:8080"

    @property
    def cors_origins(self) -> list:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    # ---- Multilingual spaCy model ----
    # Change to e.g. "xx_ent_wiki_sm" (multilingual) or "de_core_news_sm" (German).
    # Install extra models with: python -m spacy download <model_name>
    spacy_language_model: str = "en_core_web_sm"

    # ---- DeBERTa-v3 NLI scorer ----
    nli_enabled: bool = True
    nli_model: str = "cross-encoder/nli-deberta-v3-small"
    nli_confidence_threshold: float = 0.65   # Use NLI result when confidence > this

    # ---- HMM reliability tracker ----
    hmm_enabled: bool = True

    # ---- Reward system ----
    reward_system_enabled: bool = True
    reward_alpha: float = 1.0
    reward_beta: float = 2.0
    reward_gamma: float = 2.0
    reward_r0: float = 0.20

    # ---- Domain ingestion API keys (optional) ----
    cap_api_key: str = ""       # Caselaw Access Project (legal cases)

    # ---- Coreference resolution ----
    coref_enabled: bool = True

    # ---- Audit ----
    audit_log_path: str = "./audit_trail.jsonl"


@lru_cache
def get_settings() -> Settings:
    return Settings()
