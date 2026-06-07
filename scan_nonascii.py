#!/usr/bin/env python3
"""Find all non-ASCII characters in JSX/JS source files."""
import glob, os, sys
sys.stdout.reconfigure(encoding='utf-8')

for pattern in ['v4/frontend/src/**/*.jsx', 'v4/frontend/src/**/*.js']:
    for fp in glob.glob(pattern, recursive=True):
        with open(fp, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            for j, ch in enumerate(line):
                if ord(ch) > 127 and ch != '\ufeff':  # skip BOM
                    context = line[max(0,j-15):j+15].strip()
                    # Make context ASCII-safe for printing
                    safe = ''.join(c if ord(c) < 128 else f'[U+{ord(c):04X}]' for c in context)
                    print(f'{os.path.basename(fp)}:{i+1} U+{ord(ch):04X} => {safe}')
