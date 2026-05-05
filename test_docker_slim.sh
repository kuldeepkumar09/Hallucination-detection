#!/usr/bin/env bash
# Smoke test for Dockerfile.slim — validates the CPU-only image end-to-end.
# Run after: docker build -f Dockerfile.slim -t hallucheck-slim .
#
# Usage: bash test_docker_slim.sh
# Exit code: 0 = all checks passed, 1 = at least one check failed

set -euo pipefail

IMAGE="hallucheck-slim"
CONTAINER="hallucheck-smoke"
PORT=18080
BASE="http://localhost:${PORT}"
PASS=0
FAIL=0

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

ok()   { echo -e "${GREEN}PASS${NC} $1"; ((PASS++)); }
fail() { echo -e "${RED}FAIL${NC} $1"; ((FAIL++)); }
info() { echo -e "${YELLOW}INFO${NC} $1"; }

cleanup() {
    info "Stopping container..."
    docker rm -f "$CONTAINER" 2>/dev/null || true
}
trap cleanup EXIT

# ── Step 1: confirm image exists ──────────────────────────────────────────────
if docker image inspect "$IMAGE" &>/dev/null; then
    SIZE=$(docker image inspect "$IMAGE" --format='{{.Size}}' | awk '{printf "%.1f GB", $1/1073741824}')
    ok "Image exists — size: $SIZE"
    # Warn if image exceeds 5 GB target
    SIZE_BYTES=$(docker image inspect "$IMAGE" --format='{{.Size}}')
    if [ "$SIZE_BYTES" -gt 5368709120 ]; then
        fail "Image exceeds 5 GB target (got $SIZE) — check requirements.txt for CUDA wheels"
    else
        ok "Image size within 5 GB target"
    fi
else
    fail "Image '$IMAGE' not found — run: docker build -f Dockerfile.slim -t $IMAGE ."
    exit 1
fi

# ── Step 2: start container ───────────────────────────────────────────────────
info "Starting container on port $PORT..."
docker rm -f "$CONTAINER" 2>/dev/null || true
docker run -d \
    --name "$CONTAINER" \
    -p "${PORT}:8080" \
    --env-file .env \
    -e NLI_ONLY_MODE=true \
    -e FAST_MODE=true \
    -e RERANKER_ENABLED=false \
    -e API_KEY=smoke-test-key \
    "$IMAGE"

# ── Step 3: wait for health check ─────────────────────────────────────────────
info "Waiting for /health (up to 90s)..."
for i in $(seq 1 18); do
    if curl -sf "${BASE}/health" &>/dev/null; then
        ok "/health responded (attempt $i)"
        break
    fi
    if [ "$i" -eq 18 ]; then
        fail "/health never responded after 90s"
        docker logs "$CONTAINER" --tail 30
        exit 1
    fi
    sleep 5
done

# ── Step 4: /health payload ───────────────────────────────────────────────────
HEALTH=$(curl -sf "${BASE}/health")
if echo "$HEALTH" | grep -q '"status"'; then
    ok "/health returns JSON with status field"
else
    fail "/health response missing status field: $HEALTH"
fi

# ── Step 5: /status endpoint ──────────────────────────────────────────────────
STATUS=$(curl -sf "${BASE}/status" -H "X-API-Key: smoke-test-key" 2>/dev/null || echo "FAILED")
if echo "$STATUS" | grep -q '"version"'; then
    ok "/status returns version field"
else
    fail "/status failed or missing version: ${STATUS:0:200}"
fi

# ── Step 6: /verify endpoint ──────────────────────────────────────────────────
VERIFY=$(curl -sf -X POST "${BASE}/verify" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: smoke-test-key" \
    -d '{"text":"The Earth orbits the Sun.","model":"test"}' \
    --max-time 30 2>/dev/null || echo "FAILED")

if echo "$VERIFY" | grep -q '"total_claims"'; then
    ok "/verify returns audit JSON"
else
    fail "/verify failed or malformed: ${VERIFY:0:300}"
fi

# ── Step 7: non-root user ─────────────────────────────────────────────────────
WHOAMI=$(docker exec "$CONTAINER" whoami 2>/dev/null || echo "unknown")
if [ "$WHOAMI" = "appuser" ]; then
    ok "Running as non-root user: appuser"
else
    fail "Expected appuser, got: $WHOAMI"
fi

# ── Step 8: no GPU dependency ─────────────────────────────────────────────────
GPU_CHK=$(docker exec "$CONTAINER" python -c "import torch; print(torch.cuda.is_available())" 2>/dev/null || echo "error")
if [ "$GPU_CHK" = "False" ]; then
    ok "torch.cuda.is_available() = False (CPU-only confirmed)"
else
    fail "Unexpected CUDA state in slim image: $GPU_CHK"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "────────────────────────────────────"
echo -e "Results: ${GREEN}${PASS} passed${NC}  ${RED}${FAIL} failed${NC}"
echo "────────────────────────────────────"

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
