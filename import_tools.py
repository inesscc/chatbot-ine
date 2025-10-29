#!/usr/bin/env python3
"""
Open WebUI Tool and Model Importer
Imports tools and models from JSON export files into the Open WebUI database during container startup.
"""

import json
import sqlite3
import sys
import os

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
        conn = sqlite3.connect(db_path)
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

def import_models_from_json(json_file_path, db_path):
    """
    Import models from JSON export file into Open WebUI database.
    
    :param json_file_path: Path to the models export JSON file
    :param db_path: Path to the Open WebUI database file
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
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if model table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='model';")
        if not cursor.fetchone():
            print("❌ Model table does not exist in database")
            return False
        
        imported_count = 0
        updated_count = 0
        
        for model in models_data:
            model_id = model.get('id')
            if not model_id:
                print("⚠️  Skipping model without ID")
                continue
            
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
                    model.get('access_control'),
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
                    model.get('access_control'),
                    model.get('updated_at'),
                    model.get('created_at'),
                    model.get('is_active', True)
                ))
                imported_count += 1
                print(f"✅ Imported model: {model.get('name', model_id)}")
        
        conn.commit()
        conn.close()
        
        print(f"🎉 Model import completed! Imported: {imported_count}, Updated: {updated_count}")
        return True
        
    except Exception as e:
        print(f"❌ Error importing models: {e}")
        return False

if __name__ == "__main__":
    # Default paths
    tools_json = "/app/postgres-tool-export.json"
    models_json = "/app/models-export.json"
    db_file = "/app/backend/data/webui.db"
    
    # Override with command line arguments if provided
    if len(sys.argv) > 1:
        tools_json = sys.argv[1]
    if len(sys.argv) > 2:
        models_json = sys.argv[2]
    if len(sys.argv) > 3:
        db_file = sys.argv[3]
    
    # Import tools and models
    tools_success = import_tools_from_json(tools_json, db_file)
    models_success = import_models_from_json(models_json, db_file)
    
    # Exit with success only if both imports succeeded
    success = tools_success and models_success
    sys.exit(0 if success else 1)
