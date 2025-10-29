#!/usr/bin/env python3
"""
Update postgres-tool-export.json with the current postgres_llm_tool.py content
"""

import json

# Read the current tool content
with open('/home/jeconchao/repos/oui/postgres_llm_tool.py', 'r') as f:
    current_tool_content = f.read()

# Read the existing tools export
with open('/home/jeconchao/repos/oui/postgres-tool-export.json', 'r') as f:
    tools_export = json.load(f)

# Update the postgres tool content
for tool in tools_export:
    if tool['id'] == 'postgres_database_tool':
        tool['content'] = current_tool_content
        print(f"Updated tool: {tool['name']}")
        break

# Write back the updated export
with open('/home/jeconchao/repos/oui/postgres-tool-export.json', 'w') as f:
    json.dump(tools_export, f, indent=2)

print("✅ tools-export.json updated successfully!")
