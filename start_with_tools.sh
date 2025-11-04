#!/bin/bash
set -e

echo "🚀 Starting Open WebUI with automatic tool import..."

# Start Open WebUI in the background
echo "📦 Starting Open WebUI backend..."
/app/backend/start.sh &

# Get the PID of the background process
BACKEND_PID=$!

# Wait for Open WebUI to start and database to be available
echo "⏳ Waiting for Open WebUI to initialize..."
sleep 10

# Import tools and models if the export files exist
echo "🔧 Importing tools and models from export files..."
python3 /app/import_tools.py /app/postgres-tool-export.json /app/models-export.json /app/backend/data/webui.db

echo "✅ Open WebUI startup complete!"

# Wait for the backend process to finish
wait $BACKEND_PID
