#!/usr/bin/env python3
"""Phase 3: Strip ALL remaining non-ASCII from JSX/JS source files.
Only ASCII (0x00-0x7F) should remain. Comments get cleaned, strings get cleaned."""
import glob, os, sys, re
sys.stdout.reconfigure(encoding='utf-8')

def strip_nonascii(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    original = content

    # Specific known patterns first
    content = content.replace('\u201c', '"')     # left double quote
    content = content.replace('\u201d', '"')     # right double quote  
    content = content.replace('\u2018', "'")     # left single quote
    content = content.replace('\u2019', "'")     # right single quote
    content = content.replace('\u2014', ' - ')   # em-dash
    content = content.replace('\u2013', '-')     # en-dash
    content = content.replace('\u2192', '->')    # right arrow
    content = content.replace('\u2190', '<-')    # left arrow
    content = content.replace('\u00b7', ' - ')   # middle dot
    content = content.replace('\u2022', '-')     # bullet
    content = content.replace('\u2026', '...')   # ellipsis
    content = content.replace('\u00d7', 'x')     # multiplication
    content = content.replace('\u00a9', '(c)')   # copyright
    content = content.replace('\u2500', '-')     # box drawing
    content = content.replace('\u2550', '=')     # double box drawing
    content = content.replace('\u2605', '*')     # star
    content = content.replace('\u2713', 'v')     # check mark
    content = content.replace('\u2717', 'x')     # ballot x
    content = content.replace('\u00a0', ' ')     # non-breaking space
    
    # Corrupted ellipsis remnant (the bytes of ... got partially decoded)
    content = content.replace('\u201e', '...')   # double low-9 quotation (misread ellipsis)
    content = content.replace('\u00a6', '...')   # broken bar -> was ellipsis
    
    # Now strip any remaining non-ASCII character
    # Replace with empty string (for emoji remnants, decorative chars)
    # but keep spaces/structure intact
    result = []
    for ch in content:
        if ord(ch) < 128:
            result.append(ch)
        elif ch == '\ufeff':
            pass  # BOM - skip
        else:
            pass  # skip all non-ASCII
    
    content = ''.join(result)
    
    # Clean up double/triple spaces from removals (but preserve indentation)
    lines = content.split('\n')
    cleaned = []
    for line in lines:
        # Preserve leading whitespace, clean internal multiple spaces
        stripped = line.lstrip()
        indent = line[:len(line) - len(stripped)]
        stripped = re.sub(r'  +', ' ', stripped)
        # Fix common artifacts from removal: "'  Getting" -> "'Getting"
        stripped = re.sub(r"' +([A-Z])", r"'\1", stripped)
        cleaned.append(indent + stripped)
    
    content = '\n'.join(cleaned)
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
        return True
    return False


patterns = [
    'v4/frontend/src/**/*.jsx',
    'v4/frontend/src/**/*.js',
]

fixed = 0
for pattern in patterns:
    for fp in glob.glob(pattern, recursive=True):
        if strip_nonascii(fp):
            print(f'  Fixed: {os.path.basename(fp)}')
            fixed += 1

print(f'\nPhase 3: {fixed} files cleaned to pure ASCII')
