import json
import sys

logfile = r'C:\Users\MIT\.gemini\antigravity\brain\e27c796a-f44b-4c27-9264-cc5ca4aa33bd\.system_generated\tasks\task-84.log'
with open(logfile, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

parts = content.split('=== RESULTS ===\n')

print("=== LOG OUTPUT ===")
# Find the fallback logs
for line in parts[0].split('\n'):
    if '[Fallback]' in line or '[Orchestrator]' in line or 'Signal significance floor' in line:
        print(line)

