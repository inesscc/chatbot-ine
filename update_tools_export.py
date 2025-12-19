#!/usr/bin/env python3
"""
Update postgres-tool-export.json with the current postgres_llm_tool.py content
"""

import json
import os
import time

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Read the current tool content
with open('postgres_llm_tool.py', 'r') as f:
    current_tool_content = f.read()

# Read the existing tools export
with open('postgres-tool-export.json', 'r') as f:
    tools_export = json.load(f)

# Update the postgres tool content
for tool in tools_export:
    if tool['id'] == 'postgres_database_tool':
        tool['content'] = current_tool_content
        # Update the timestamp to current time - this ensures the tool is detected as changed
        tool['updated_at'] = int(time.time())
        print(f"Updated tool: {tool['name']}")
        print(f"New timestamp: {tool['updated_at']}")
        break

# Write back the updated export
with open('postgres-tool-export.json', 'w') as f:
    json.dump(tools_export, f, indent=2)

print("✅ postgres-tool-export.json updated successfully!")
