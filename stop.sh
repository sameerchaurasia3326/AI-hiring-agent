#!/bin/bash
# Stop all Hiring AI processes
echo "🛑 Stopping Hiring AI..."
pkill -f "uvicorn src.api.main" 2>/dev/null && echo "  ✅ API stopped" || echo "  ℹ️  API was not running"
pkill -f "celery -A src.scheduler.celery_app" 2>/dev/null && echo "  ✅ Celery stopped" || echo "  ℹ️  Celery was not running"
echo "Done."
