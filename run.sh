#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "============================================================"
echo " Starting Frontdesk System (Backend + Frontend)"
echo "============================================================"

# Ensure virtualenv exists
if [ ! -d "backend/venv" ]; then
    echo "[1/4] Creating Python virtual environment..."
    python3 -m venv backend/venv
    source backend/venv/bin/activate
    pip install --upgrade pip
    pip install -r backend/requirements.txt
else
    source backend/venv/bin/activate
fi

# Ensure frontend dependencies exist
if [ ! -d "frontend/node_modules" ]; then
    echo "[2/4] Installing frontend npm packages..."
    (cd frontend && npm install)
fi

echo "[3/4] Launching FastAPI Backend on http://0.0.0.0:8000..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend &
BACKEND_PID=$!

echo "[4/4] Launching Vite Frontend on http://0.0.0.0:5173..."
(cd frontend && npx vite --host 0.0.0.0 --port 5173) &
FRONTEND_PID=$!

cleanup() {
    echo ""
    echo "Stopping Frontdesk services (PID $BACKEND_PID, $FRONTEND_PID)..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
}

trap cleanup EXIT INT TERM

echo ""
echo "Frontdesk is running!"
echo "  Frontend Web UI:   http://localhost:5173"
echo "  Backend API Docs:  http://localhost:8000/docs"
echo "  Health Check:      http://localhost:8000/api/health"
echo "Press Ctrl+C to terminate both servers."

wait
