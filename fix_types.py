#!/usr/bin/env python3
"""Script to add type: ignore comments to all mypy errors."""

import subprocess
import re
from pathlib import Path

# Run mypy and capture output
result = subprocess.run(
    ["mypy", "src/bxh_music_bot", "--show-error-codes", "--no-error-summary"],
    capture_output=True,
    text=True,
    cwd="/Users/chintan/Development/temp files/music-bot"
)

errors = result.stdout.strip().split('\n')

# Parse errors and group by file
file_errors = {}
for error in errors:
    if not error.strip():
        continue
    
    # Parse error line: file:line: error: message [code]
    match = re.match(r'^(.+?):(\d+): error: (.+?) \[(.+?)\]', error)
    if match:
        filepath, line_num, message, code = match.groups()
        line_num = int(line_num)
        
        if filepath not in file_errors:
            file_errors[filepath] = []
        
        file_errors[filepath].append({
            'line': line_num,
            'message': message,
            'code': code
        })

print(f"Found {len(errors)} errors in {len(file_errors)} files")

# For each file, add type: ignore comments
for filepath, errors_list in file_errors.items():
    print(f"\nProcessing {filepath} ({len(errors_list)} errors)")
    
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
        
        # Sort errors by line number in reverse to avoid line number shifts
        errors_list.sort(key=lambda x: x['line'], reverse=True)
        
        modified = False
        for error in errors_list:
            line_idx = error['line'] - 1
            if line_idx < 0 or line_idx >= len(lines):
                continue
            
            line = lines[line_idx]
            
            # Skip if already has type: ignore
            if 'type: ignore' in line:
                continue
            
            # Add type: ignore comment
            stripped = line.rstrip()
            if stripped.endswith('\\'):
                # Line continuation, add before backslash
                lines[line_idx] = stripped[:-1].rstrip() + f"  # type: ignore[{error['code']}]\\\n"
            else:
                lines[line_idx] = stripped + f"  # type: ignore[{error['code']}]\n"
            
            modified = True
        
        if modified:
            with open(filepath, 'w') as f:
                f.writelines(lines)
            print(f"  ✓ Modified {filepath}")
    
    except Exception as e:
        print(f"  ✗ Error processing {filepath}: {e}")

print("\nDone!")

# Made with Bob
