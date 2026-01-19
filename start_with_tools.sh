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

# Wait for Ollama to be ready
echo "⏳ Waiting for Ollama service..."
until ollama list &> /dev/null; do
  echo "Ollama not ready yet, waiting..."
  sleep 2
done
echo "✅ Ollama service is ready!"

# # Create custom model from Modelfile if it doesn't exist
# MODEL_NAME="nemotron-3-nano-q3"
# if ollama list | grep -q "^${MODEL_NAME}"; then
#   echo "✅ Model '${MODEL_NAME}' already exists, skipping creation"
# else
#   echo "🤖 Creating model '${MODEL_NAME}' from Modelfile..."
#   cd /app/backend/hf_models/${MODEL_NAME}
#   ollama create ${MODEL_NAME} 
#   echo "✅ Model '${MODEL_NAME}' created successfully!"
# fi

# MODEL_NAME="nemotron-3-nano-q4"
# if ollama list | grep -q "^${MODEL_NAME}"; then
#   echo "✅ Model '${MODEL_NAME}' already exists, skipping creation"
# else
#   echo "🤖 Creating model '${MODEL_NAME}' from Modelfile..."
#   cd /app/backend/hf_models/${MODEL_NAME}
#   ollama create ${MODEL_NAME} 
#   echo "✅ Model '${MODEL_NAME}' created successfully!"
# fi


# Import tools, models, and config if the export files exist
echo "🔧 Importing tools, models, and config from export files..."
python3 /app/import_tools.py /app/postgres-tool-export.json /app/models-export.json /app/config-export.json /app/backend/data/webui.db

echo "✅ Open WebUI startup complete!"

# Wait for the backend process to finish
wait $BACKEND_PID
