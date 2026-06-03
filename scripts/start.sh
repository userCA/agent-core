#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

PORT="${PORT:-8001}"

echo "=== 咪兔 Agent Server ==="
echo "Project: $PROJECT_ROOT"
echo "Port:    $PORT"

# 1. Kill all old processes (server + MCP children)
echo "[1/4] Cleaning up old processes..."
pkill -9 -f "scene.http_sse.server" 2>/dev/null || true
pkill -9 -f "mcp-server\|tavily-mcp\|mcp-amap" 2>/dev/null || true
# Ensure port is free
lsof -ti:"$PORT" 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1

# 2. Build frontend
echo "[2/4] Building frontend..."
cd "$PROJECT_ROOT/scene/http_sse/static"
npm run build --silent 2>&1 | tail -1
cd "$PROJECT_ROOT"

# 3. Start server
echo "[3/4] Starting server..."
trap 'echo "Shutting down..."; pkill -P $$ 2>/dev/null; exit 0' INT TERM

PORT=$PORT python -m scene.http_sse.server &
SERVER_PID=$!

# 4. Wait for readiness
echo "[4/4] Waiting for server ready..."
for i in $(seq 1 60); do
    if curl -s "http://localhost:$PORT/models" > /dev/null 2>&1; then
        echo ""
        echo "=== Server ready ==="
        echo "  http://localhost:$PORT"
        echo "  PID: $SERVER_PID"
        echo "  Log: tail -f /tmp/agent-server.log"
        wait $SERVER_PID
        exit 0
    fi
    sleep 1
done

echo "ERROR: Server failed to start within 60s"
kill $SERVER_PID 2>/dev/null
exit 1
