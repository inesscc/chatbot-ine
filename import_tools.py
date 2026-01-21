#!/usr/bin/env python3
"""
Open WebUI Tool and Model Importer
Imports tools and models from JSON export files into the Open WebUI database during container startup.
"""

import json
import sqlite3
import sys
import os
import re
import time

def load_system_prompt(params, prompts_base_path="/app/"):
    """
    Load system prompt based on priority order:
    1. Inline override: if params.system exists and is non-empty, use it
    2. File override: if params.system_prompt_file exists, load from that file
    3. Default: load from {prompts_base_path}/system_prompt.md

    :param params: The model params dict
    :param prompts_base_path: Base path for prompt files (default: /app/)
    :return: Tuple of (prompt_content, source_description)
    """
    # Priority 1: Inline override
    if params.get('system') and params['system'].strip():
        return params['system'], "inline"

    # Priority 2: File override
    if params.get('system_prompt_file'):
        file_path = os.path.join(prompts_base_path, params['system_prompt_file'])
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return content, f"file:{params['system_prompt_file']}"
            except Exception as e:
                print(f"⚠️  Error reading prompt file {file_path}: {e}")
        else:
            print(f"⚠️  Prompt file not found: {file_path}")

    # Priority 3: Default
    default_path = os.path.join(prompts_base_path, "system_prompt.md")
    if os.path.exists(default_path):
        try:
            with open(default_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content, "default:system_prompt.md"
        except Exception as e:
            print(f"⚠️  Error reading default prompt file {default_path}: {e}")

    # No prompt found
    return None, "none"


def import_tools_from_json(json_file_path, db_path):
    """
    Import tools from JSON export file into Open WebUI database.
    
    :param json_file_path: Path to the tools export JSON file
    :param db_path: Path to the Open WebUI database file
    """
    print(f"🔧 Starting tool import from {json_file_path}")
    
    # Check if JSON file exists
    if not os.path.exists(json_file_path):
        print(f"❌ JSON file not found: {json_file_path}")
        return False
    
    # Load tools from JSON file
    try:
        with open(json_file_path, 'r') as f:
            tools_data = json.load(f)
        print(f"📖 Loaded {len(tools_data)} tools from JSON file")
    except Exception as e:
        print(f"❌ Error reading JSON file: {e}")
        return False
    
    # Wait for database to be available
    max_retries = 30
    for i in range(max_retries):
        if os.path.exists(db_path):
            break
        print(f"⏳ Waiting for database... ({i+1}/{max_retries})")
        import time
        time.sleep(1)
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found after waiting: {db_path}")
        return False
    
    # Connect to database and import tools
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        cursor = conn.cursor()
        
        # Check if tool table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tool';")
        if not cursor.fetchone():
            print("❌ Tool table does not exist in database")
            return False
        
        imported_count = 0
        updated_count = 0
        
        for tool in tools_data:
            tool_id = tool.get('id')
            if not tool_id:
                print("⚠️  Skipping tool without ID")
                continue
            
            # Check if tool already exists
            cursor.execute("SELECT id FROM tool WHERE id = ?", (tool_id,))
            exists = cursor.fetchone()
            
            if exists:
                # Update existing tool
                cursor.execute("""
                    UPDATE tool 
                    SET name = ?, content = ?, specs = ?, meta = ?, 
                        access_control = ?, updated_at = ?
                    WHERE id = ?
                """, (
                    tool.get('name'),
                    tool.get('content'),
                    json.dumps(tool.get('specs', [])),
                    json.dumps(tool.get('meta', {})),
                    tool.get('access_control'),
                    tool.get('updated_at'),
                    tool_id
                ))
                updated_count += 1
                print(f"🔄 Updated tool: {tool.get('name', tool_id)}")
            else:
                # Insert new tool
                cursor.execute("""
                    INSERT INTO tool (id, user_id, name, content, specs, meta, 
                                    access_control, updated_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tool_id,
                    tool.get('user_id'),
                    tool.get('name'),
                    tool.get('content'),
                    json.dumps(tool.get('specs', [])),
                    json.dumps(tool.get('meta', {})),
                    tool.get('access_control'),
                    tool.get('updated_at'),
                    tool.get('created_at')
                ))
                imported_count += 1
                print(f"✅ Imported tool: {tool.get('name', tool_id)}")
        
        conn.commit()
        conn.close()
        
        print(f"🎉 Tool import completed! Imported: {imported_count}, Updated: {updated_count}")
        return True
        
    except Exception as e:
        print(f"❌ Error importing tools: {e}")
        return False

def import_models_from_json(json_file_path, db_path, prompts_base_path="/app/"):
    """
    Import models from JSON export file into Open WebUI database.

    :param json_file_path: Path to the models export JSON file
    :param db_path: Path to the Open WebUI database file
    :param prompts_base_path: Base path for system prompt files (default: /app/)
    """
    print(f"🤖 Starting model import from {json_file_path}")
    
    # Check if JSON file exists
    if not os.path.exists(json_file_path):
        print(f"❌ JSON file not found: {json_file_path}")
        return False
    
    # Load models from JSON file
    try:
        with open(json_file_path, 'r') as f:
            models_data = json.load(f)
        print(f"📖 Loaded {len(models_data)} models from JSON file")
    except Exception as e:
        print(f"❌ Error reading JSON file: {e}")
        return False
    
    # Wait for database to be available
    max_retries = 30
    for i in range(max_retries):
        if os.path.exists(db_path):
            break
        print(f"⏳ Waiting for database... ({i+1}/{max_retries})")
        import time
        time.sleep(1)
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found after waiting: {db_path}")
        return False
    
    # Connect to database and import models
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        cursor = conn.cursor()
        
        # Check if model table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='model';")
        if not cursor.fetchone():
            print("❌ Model table does not exist in database")
            return False
        
        imported_count = 0
        updated_count = 0
        deleted_count = 0

        # Get all model IDs from JSON file
        json_model_ids = {model.get('id') for model in models_data if model.get('id')}

        # Delete models not in JSON file
        cursor.execute("SELECT id FROM model")
        existing_models = cursor.fetchall()
        for (model_id,) in existing_models:
            if model_id not in json_model_ids:
                cursor.execute("DELETE FROM model WHERE id = ?", (model_id,))
                deleted_count += 1
                print(f"🗑️  Deleted model: {model_id}")

        for model in models_data:
            model_id = model.get('id')
            if not model_id:
                print("⚠️  Skipping model without ID")
                continue

            # Load system prompt for this model
            params = model.get('params', {})
            prompt_content, prompt_source = load_system_prompt(params, prompts_base_path)
            if prompt_content:
                params['system'] = prompt_content
                model['params'] = params
                print(f"📝 Loaded system prompt for {model_id} from {prompt_source}")
            elif prompt_source == "none":
                print(f"⚠️  No system prompt found for {model_id}")

            # Check if model already exists
            cursor.execute("SELECT id FROM model WHERE id = ?", (model_id,))
            exists = cursor.fetchone()
            
            if exists:
                # Update existing model
                cursor.execute("""
                    UPDATE model
                    SET name = ?, meta = ?, params = ?,
                        access_control = ?, updated_at = ?, is_active = ?
                    WHERE id = ?
                """, (
                    model.get('name'),
                    json.dumps(model.get('meta', {})),
                    json.dumps(model.get('params', {})),
                    json.dumps(model.get('access_control')) if model.get('access_control') is not None else None,
                    model.get('updated_at'),
                    model.get('is_active', True),
                    model_id
                ))
                updated_count += 1
                print(f"🔄 Updated model: {model.get('name', model_id)}")
            else:
                # Insert new model
                cursor.execute("""
                    INSERT INTO model (id, user_id, base_model_id, name, meta, params,
                                     access_control, updated_at, created_at, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    model_id,
                    model.get('user_id'),
                    model.get('base_model_id'),
                    model.get('name'),
                    json.dumps(model.get('meta', {})),
                    json.dumps(model.get('params', {})),
                    json.dumps(model.get('access_control')) if model.get('access_control') is not None else None,
                    model.get('updated_at'),
                    model.get('created_at'),
                    model.get('is_active', True)
                ))
                imported_count += 1
                print(f"✅ Imported model: {model.get('name', model_id)}")
        
        conn.commit()
        conn.close()
        
        print(f"🎉 Model import completed! Imported: {imported_count}, Updated: {updated_count}, Deleted: {deleted_count}")
        return True
        
    except Exception as e:
        print(f"❌ Error importing models: {e}")
        return False

def substitute_env_vars(obj):
    """
    Recursively substitute environment variable placeholders in a JSON object.
    Placeholders are in the format ${VAR_NAME}.
    """
    if isinstance(obj, str):
        # Find all ${VAR_NAME} patterns and substitute
        pattern = r'\$\{([^}]+)\}'
        def replace_var(match):
            var_name = match.group(1)
            value = os.environ.get(var_name, '')
            if not value:
                print(f"⚠️  Environment variable {var_name} not set")
            return value
        return re.sub(pattern, replace_var, obj)
    elif isinstance(obj, dict):
        return {k: substitute_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [substitute_env_vars(item) for item in obj]
    else:
        return obj

def update_openai_config_via_api(config_data, db_path, base_url="http://localhost:8080", secret_key_dir="/app/backend"):
    """
    Update OpenAI config via the Open WebUI API.
    This ensures the in-memory config cache is refreshed.

    :param config_data: The full config dict (with openai section)
    :param db_path: Path to the Open WebUI database file
    :param base_url: Open WebUI base URL
    :param secret_key_dir: Directory containing .webui_secret_key file
    """
    import uuid
    import requests

    openai_config = config_data.get('openai', {})
    if not openai_config:
        print("⚠️  No OpenAI config found, skipping API update")
        return True

    print(f"🔄 Updating OpenAI config via API...")

    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        cursor = conn.cursor()

        # Find an admin user
        cursor.execute("SELECT id FROM user WHERE role = 'admin' LIMIT 1")
        admin_row = cursor.fetchone()
        if not admin_row:
            print("⚠️  No admin user found, skipping API update")
            conn.close()
            return True

        admin_id = admin_row[0]
        conn.close()

        # Read WEBUI_SECRET_KEY from file
        secret_key_path = os.path.join(secret_key_dir, ".webui_secret_key")
        if not os.path.exists(secret_key_path):
            print(f"⚠️  Secret key file not found: {secret_key_path}")
            return False

        with open(secret_key_path, 'r') as f:
            webui_secret_key = f.read().strip()

        # Generate a JWT token for the admin user
        try:
            import jwt
            from datetime import datetime, timedelta, timezone

            payload = {
                "id": admin_id,
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
                "jti": str(uuid.uuid4())
            }
            token = jwt.encode(payload, webui_secret_key, algorithm="HS256")
            print(f"✅ Generated JWT token for admin user")
        except ImportError:
            print("⚠️  PyJWT not installed, trying with jose")
            try:
                from jose import jwt
                from datetime import datetime, timedelta, timezone

                payload = {
                    "id": admin_id,
                    "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
                    "jti": str(uuid.uuid4())
                }
                token = jwt.encode(payload, webui_secret_key, algorithm="HS256")
                print(f"✅ Generated JWT token for admin user (jose)")
            except ImportError:
                print("⚠️  Neither PyJWT nor python-jose installed, cannot generate JWT")
                return False

        # Prepare the API request
        api_configs = openai_config.get('api_configs', {})
        api_base_urls = openai_config.get('api_base_urls', [])
        api_keys = openai_config.get('api_keys', [])
        enable_openai = openai_config.get('enable', True)

        payload = {
            "ENABLE_OPENAI_API": enable_openai,
            "OPENAI_API_BASE_URLS": api_base_urls,
            "OPENAI_API_KEYS": api_keys,
            "OPENAI_API_CONFIGS": api_configs
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # Wait for the API to be ready
        max_retries = 30
        for i in range(max_retries):
            try:
                response = requests.get(f"{base_url}/health", timeout=5)
                if response.status_code == 200:
                    break
            except requests.exceptions.RequestException:
                pass
            print(f"⏳ Waiting for API to be ready... ({i+1}/{max_retries})")
            time.sleep(2)

        # Make the API call
        response = requests.post(
            f"{base_url}/openai/config/update",
            json=payload,
            headers=headers,
            timeout=30
        )

        if response.status_code == 200:
            print(f"✅ OpenAI config updated via API successfully")
            return True
        else:
            print(f"⚠️  API call returned status {response.status_code}: {response.text}")
            return False

    except Exception as e:
        print(f"⚠️  Error updating OpenAI config via API: {e}")
        import traceback
        traceback.print_exc()
        return False


def import_config_from_json(json_file_path, db_path):
    """
    Import config from JSON export file into Open WebUI database.
    Supports environment variable substitution for sensitive values like API keys.

    :param json_file_path: Path to the config export JSON file
    :param db_path: Path to the Open WebUI database file
    :return: Tuple of (success, config_data) where config_data is the loaded config
    """
    print(f"⚙️  Starting config import from {json_file_path}")

    # Check if JSON file exists
    if not os.path.exists(json_file_path):
        print(f"❌ JSON file not found: {json_file_path}")
        return False, None

    # Load config from JSON file
    try:
        with open(json_file_path, 'r') as f:
            config_data = json.load(f)
        print(f"📖 Loaded config from JSON file")
    except Exception as e:
        print(f"❌ Error reading JSON file: {e}")
        return False, None

    # Substitute environment variables
    config_data = substitute_env_vars(config_data)

    # Wait for database to be available
    max_retries = 30
    for i in range(max_retries):
        if os.path.exists(db_path):
            break
        print(f"⏳ Waiting for database... ({i+1}/{max_retries})")
        import time
        time.sleep(1)

    if not os.path.exists(db_path):
        print(f"❌ Database not found after waiting: {db_path}")
        return False, None

    # Connect to database and import config
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        cursor = conn.cursor()

        # Check if config table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config';")
        if not cursor.fetchone():
            print("❌ Config table does not exist in database")
            return False, None

        # Check if config row exists (id=1)
        cursor.execute("SELECT id FROM config WHERE id = 1")
        exists = cursor.fetchone()

        config_json = json.dumps(config_data)

        if exists:
            # Update existing config
            cursor.execute("""
                UPDATE config
                SET data = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (config_json,))
            print("🔄 Updated existing config")
        else:
            # Insert new config
            cursor.execute("""
                INSERT INTO config (id, data, version, created_at, updated_at)
                VALUES (1, ?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (config_json,))
            print("✅ Imported new config")

        conn.commit()
        conn.close()

        print("🎉 Config import completed!")
        return True, config_data

    except Exception as e:
        print(f"❌ Error importing config: {e}")
        return False, None

if __name__ == "__main__":
    import time

    # Default paths
    tools_json = "/app/exports/postgres-tool-export.json"
    models_json = "/app/exports/models-export.json"
    config_json = "/app/exports/config-export.json"
    db_file = "/app/backend/data/webui.db"

    # Override with command line arguments if provided
    if len(sys.argv) > 1:
        tools_json = sys.argv[1]
    if len(sys.argv) > 2:
        models_json = sys.argv[2]
    if len(sys.argv) > 3:
        config_json = sys.argv[3]
    if len(sys.argv) > 4:
        db_file = sys.argv[4]

    # Import tools, models, and config with delays to prevent database locks
    tools_success = import_tools_from_json(tools_json, db_file)
    time.sleep(1)  # Wait for database to release locks

    models_success = import_models_from_json(models_json, db_file)
    time.sleep(1)  # Wait for database to release locks

    config_success, config_data = import_config_from_json(config_json, db_file)
    time.sleep(1)  # Wait for database to release locks

    # Update OpenAI config via API to refresh in-memory cache
    if config_success and config_data:
        update_openai_config_via_api(config_data, db_file)

    # Exit with success only if all imports succeeded
    success = tools_success and models_success and config_success
    sys.exit(0 if success else 1)
