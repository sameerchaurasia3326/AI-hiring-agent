#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  Hiring AI — One-Command Startup
#  Run: ./start.sh
#  This starts everything. You only need to:
#    1. Click the JD approval link sent to your email
#    2. Click the candidate selection link sent to your email
#  Everything else runs automatically.
# ─────────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

if [ -f ".venv/bin/activate" ]; then
    echo "🐍 Activating Python virtual environment..."
    source .venv/bin/activate
fi

LOG=./logs/pipeline.log
mkdir -p logs

# ── Kill any stale processes ──────────────────────────────────
echo "🧹 Stopping any existing processes..."
pkill -f "uvicorn src.api.main" 2>/dev/null || true
pkill -f "celery -A src.scheduler.celery_app" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
sleep 1

# ── Clear old log ────────────────────────────────────────────
> "$LOG"

# ── Start API server ─────────────────────────────────────────
echo "🚀 Starting API server on http://localhost:8000 ..."
PYTHONPATH=. .venv/bin/python -m uvicorn src.api.main:app \
  --host 0.0.0.0 --port 8000 \
  >> "$LOG" 2>&1 &
API_PID=$!

# ── Start Celery worker ──────────────────────────────────────
echo "⚙️  Starting Celery worker..."
PYTHONPATH=. .venv/bin/python -m celery \
  -A src.scheduler.celery_app worker \
  --loglevel=info \
  >> "$LOG" 2>&1 &
CELERY_PID=$!

# ── Start React Frontend ──────────────────────────────────────
echo "💻 Starting React frontend on http://localhost:5173 ..."
cd frontend
npm run dev >> "../$LOG" 2>&1 &
FRONTEND_PID=$!
cd ..

# ── Wait for API to become ready ─────────────────────────────
echo "⏳ Waiting for API to be ready..."
for i in $(seq 1 15); do
  if curl -s http://localhost:8000/docs > /dev/null 2>&1; then
    echo "✅ API is ready!"
    break
  fi
  sleep 1
done

# ── Done ─────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════"
echo "  ✅ Hiring AI is running!"
echo "  📋 API Docs:  http://localhost:8000/docs"
echo "  📝 Live logs: tail -f $LOG"
echo "  🛑 To stop:   ./stop.sh"
echo "════════════════════════════════════════════"
echo ""
echo "📡 Live pipeline log (Ctrl+C to exit, system keeps running):"
echo "─────────────────────────────────────────────"
tail -f "$LOG"
