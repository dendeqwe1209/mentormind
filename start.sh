#!/usr/bin/env bash

# ==============================================================================
# MentorMind Know-How AI — One-click Startup Script
# Khởi động đồng thời cả Backend (FastAPI) và Frontend (React Vite) bằng 1 lệnh.
# ==============================================================================

set -e

# Đổi thư mục làm việc về thư mục gốc của repo
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

echo "=================================================================="
echo "🚀  KHỞI ĐỘNG HỆ THỐNG MENTORMIND KNOW-HOW AI"
echo "=================================================================="

# 1. Kiểm tra và giải phóng port 8000 và 5173 nếu đang bị chiếm
echo "🔍 Kiểm tra port 8000 và 5173..."
for port in 8000 5173; do
    pid=$(lsof -ti :$port 2>/dev/null || true)
    if [ -n "$pid" ]; then
        echo "⚠️  Port $port đang chạy tiến trình PID $pid. Đang giải phóng..."
        kill -9 $pid 2>/dev/null || true
    fi
done

# 2. Kiểm tra môi trường Python (.venv)
if [ ! -d ".venv" ]; then
    echo "📦 Đang tạo virtualenv .venv..."
    python3 -m venv .venv
    .venv/bin/pip install -r mentormind/backend/requirements.txt pytest jsonschema httpx ruff
fi

# 3. Nạp sẵn dữ liệu demo nếu chưa có DB
if [ ! -f "data/work/profiles.sqlite" ]; then
    echo "📂 Nạp dữ liệu hồ sơ mẫu ban đầu (seed_demo)..."
    PYTHONPATH=. .venv/bin/python3 mentormind/knowledge_base/store/seed_demo.py
fi

# 4. Kiểm tra dependencies của Frontend
if [ ! -d "mentormind/frontend/node_modules" ]; then
    echo "📦 Cài đặt thư viện frontend..."
    npm --prefix mentormind/frontend install
fi

# Hàm dọn dẹp khi bấm Ctrl+C
cleanup() {
    echo ""
    echo "🛑 Đang dừng toàn bộ hệ thống..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    wait $BACKEND_PID 2>/dev/null || true
    wait $FRONTEND_PID 2>/dev/null || true
    echo "✅ Đã tắt an toàn Backend và Frontend."
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# 5. Khởi động Backend
echo "⚙️  Khởi động FastAPI Backend tại http://localhost:8000 ..."
PYTHONPATH=. .venv/bin/uvicorn mentormind.backend.app.main:app --port 8000 --reload &
BACKEND_PID=$!

# Chờ Backend sẵn sàng
echo "⏳ Đang kiểm tra kết nối Backend..."
until curl -s http://localhost:8000/health > /dev/null 2>&1; do
    sleep 0.5
done
echo "✅ Backend đã sẵn sàng!"

# 6. Khởi động Frontend
echo "💻 Khởi động React Vite Frontend tại http://localhost:5173 ..."
npm --prefix mentormind/frontend run dev &
FRONTEND_PID=$!

sleep 1.5

echo ""
echo "=================================================================="
echo "🎉 HỆ THỐNG ĐÃ SẴN SÀNG DEMO!"
echo "🌐 Giao diện Tablet UI : http://localhost:5173"
echo "📑 Swagger API Docs    : http://localhost:8000/docs"
echo "⚡ Nhấn [Ctrl + C] bất cứ lúc nào để dừng cả 2 server."
echo "=================================================================="
echo ""

# Tự động mở trình duyệt trên macOS
if command -v open >/dev/null 2>&1; then
    open "http://localhost:5173"
fi

# Giữ script chạy và lắng nghe tín hiệu tắt
wait
