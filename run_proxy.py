#!/usr/bin/env python3
"""
Start the Hallucination Detection Proxy server.

The proxy is a drop-in replacement for the Anthropic API endpoint.
Point your Anthropic client at http://localhost:8080 instead of
https://api.anthropic.com.

Usage:
  python run_proxy.py
  python run_proxy.py --port 9000
  python run_proxy.py --reload   (development mode)
"""
import argparse
import logging
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Hallucination Detection Proxy")
    parser.add_argument("--host", default=None, help="Bind host (overrides .env)")
    parser.add_argument("--port", type=int, default=None, help="Bind port (overrides .env)")
    parser.add_argument("--reload", action="store_true", help="Enable hot-reload (dev mode)")
    args = parser.parse_args()

    from hallucination_middleware.config import get_settings  # noqa: PLC0415
    settings = get_settings()

    if settings.llm_provider == "anthropic" and not settings.anthropic_api_key:
        print("ERROR: LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set.")
        print("  Add your key to .env or switch to LLM_PROVIDER=ollama (free).")
        sys.exit(1)

    if settings.llm_provider == "nvidia_nim" and not settings.nvidia_nim_api_key:
        print("ERROR: LLM_PROVIDER=nvidia_nim but NVIDIA_NIM_API_KEY is not set.")
        print("  Get a free key at https://build.nvidia.com and add it to .env")
        sys.exit(1)

    host = args.host or settings.proxy_host
    port = args.port or settings.proxy_port

    print()
    print("=" * 56)
    print("   Hallucination Detection Proxy  v3.0")
    print("=" * 56)
    print(f"  Listening on   :  http://{host}:{port}")
    if settings.llm_provider == "nvidia_nim":
        print(f"  LLM Provider   :  NVIDIA NIM -> {settings.nvidia_nim_base_url}")
    elif settings.llm_provider == "ollama":
        print(f"  LLM Provider   :  Ollama (local) at {settings.ollama_base_url}")
    else:
        print(f"  LLM Provider   :  Anthropic -> {settings.anthropic_api_base}")
    print(f"  Extractor      :  {settings.extractor_model}")
    print(f"  Verifier       :  {settings.verifier_model}")
    print(f"  KB directory   :  {settings.kb_persist_dir}")
    print(f"  Audit log      :  {settings.audit_log_path}")
    print(f"  Flag threshold :  {settings.flag_threshold}")
    print(f"  Block threshold:  {settings.block_threshold}")
    print(f"  BM25           :  {'on' if settings.bm25_enabled else 'off'}")
    print(f"  Reranker       :  {'on' if settings.reranker_enabled else 'off'}")
    print(f"  Cache          :  {'on' if settings.cache_enabled else 'off'}")
    print(f"  Ensemble       :  {'on' if settings.ensemble_for_critical else 'off'}")
    print()
    print("  Client setup example:")
    print(f"    import anthropic")
    print(f"    client = anthropic.Anthropic(")
    print(f"        api_key='any-string',   # proxy injects the real key")
    print(f"        base_url='http://localhost:{port}',")
    print(f"    )")
    print()
    print("  Endpoints:  /health  /verify  /audit/recent  /audit/stats  /kb/stats  /cache/stats")
    print()
    print("  Frontend:   cd frontend && npm run dev  ->  http://localhost:5173")
    print()

    import uvicorn  # noqa: PLC0415
    uvicorn.run(
        "hallucination_middleware.proxy:app",
        host=host,
        port=port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
