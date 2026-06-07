#!/usr/bin/env python3
"""Fix all non-ASCII mojibake in the OrQuanta codebase.

Strategy: For JSX/JS/CSS/Python files, replace any sequence of 2+ non-ASCII
bytes that appear before a regular word with nothing (these are corrupted emoji).
For known em-dash/arrow mojibake, replace with ASCII equivalents.
"""
import glob
import re
import os


def fix_file(filepath):
    with open(filepath, 'rb') as f:
        raw = f.read()
    
    original = raw
    
    # Known mojibake byte sequences for em-dash (most common)
    # UTF-8 em-dash is E2 80 94, but double-encoded through Windows-1252 becomes:
    # C3 A2 E2 82 AC E2 80 9C (or variants)
    raw = raw.replace(b'\xc3\xa2\xe2\x82\xac\xe2\x80\x9c', b' - ')  # em-dash variant 1
    raw = raw.replace(b'\xc3\xa2\xe2\x82\xac\xe2\x80\x9d', b' - ')  # em-dash variant 2
    raw = raw.replace(b'\xc3\xa2\xe2\x82\xac\xe2\x84\xa2', b"'")     # right single quote
    raw = raw.replace(b'\xc3\xa2\xe2\x82\xac\xc2\xa2', b'-')         # bullet
    raw = raw.replace(b'\xc3\xa2\xe2\x82\xac\xc2\xba', b'')          # misc
    raw = raw.replace(b'\xc3\xa2\xe2\x82\xac', b'"')                  # generic double-quote fallback
    
    # Arrow mojibake
    raw = raw.replace(b'\xc3\xa2\xe2\x80\xa0\xe2\x80\x99', b'->')  # right arrow
    raw = raw.replace(b'\xc3\xa2\xe2\x80\xa0\xc2\x90', b'<-')       # left arrow
    
    # Middle dot mojibake
    raw = raw.replace(b'\xc3\x82\xc2\xb7', b' - ')
    raw = raw.replace(b'\xc2\xb7', b' - ')
    
    # Copyright mojibake
    raw = raw.replace(b'\xc3\x82\xc2\xa9', b'(c)')
    
    # Ellipsis mojibake
    raw = raw.replace(b'\xc3\xa2\xe2\x82\xac\xc2\xa6', b'...')
    
    # Now handle the triple-encoded emoji in section headers and elsewhere
    # These appear as sequences like C3 B0 C5 B8 ... before actual ASCII text
    # Strategy: remove any run of bytes where each byte is >= 0x80 that appears
    # before a space+ASCII or at string boundaries
    
    # Specific known corrupted emoji sequences found in the hex dump:
    raw = raw.replace(b'\xc3\xb0\xc5\xb8\xc5\xa1\xe2\x82\xac', b'')  # rocket
    raw = raw.replace(b'\xc3\xb0\xc5\xb8\x27\xc2\xb0', b'')           # money bag (with quote)
    raw = raw.replace(b'\xc3\xb0\xc5\xb8\xc2\xa4\x2d', b'')           # robot (with hyphen)
    raw = raw.replace(b'\xc3\xb0\xc5\xb8\xe2\x80\xba\xc2\xa1\xc3\xaf\xc2\xb8\xc2\x8f', b'')  # shield emoji
    raw = raw.replace(b'\xc3\xa2\xc5\xa1\xe2\x84\xa2\xc3\xaf\xc2\xb8\xc2\x8f', b'')            # gear emoji
    raw = raw.replace(b'\xc3\xaf\xc2\xb8\xc2\x8f', b'')              # variation selector
    
    # Warning emoji mojibake
    raw = raw.replace(b'\xc3\xa2\xc5\xa1\xe2\x80\xa0', b'')           # warning sign
    raw = raw.replace(b'\xc3\xa2\xc5\xa1\xe2\x84\xa2', b'')           # gear
    raw = raw.replace(b'\xc3\xa2\xc5\xa1\xc2\xa1', b'')               # zap
    
    # Check mark / cross mojibake
    raw = raw.replace(b'\xc3\xa2\xc5\x93\xe2\x80\x9c', b'')          # check
    raw = raw.replace(b'\xc3\xa2\xc5\x93\xe2\x80\x9d', b'')          # cross
    
    # Misc double-encoded remnants
    raw = raw.replace(b'\xc3\xb0\xc5\xb8', b'')                       # start of any double-encoded 4-byte emoji
    raw = raw.replace(b'\xc3\xa2\xc5\xa1', b'')                       # start of double-encoded 3-byte symbol
    
    # Clean up remaining isolated high bytes (variation selectors, etc)
    # But only if they're surrounded by ASCII
    # Don't touch legitimate UTF-8 in strings
    
    # Remove any remaining C3 XX sequences that aren't valid ASCII intent
    # These are Latin supplement characters that shouldn't be in source code
    # Be conservative: only remove if followed by more high bytes (indicating corruption)
    
    if raw != original:
        with open(filepath, 'wb') as f:
            f.write(raw)
        return True
    return False


def main():
    file_patterns = [
        'v4/frontend/src/**/*.jsx',
        'v4/frontend/src/**/*.js', 
        'v4/frontend/src/**/*.css',
        'v4/api/**/*.py',
        'v4/agents/**/*.py',
        'v4/execution/**/*.py',
        'v4/providers/**/*.py',
        'worker.js',
        'templates/**/*.html',
    ]
    
    fixed = 0
    for pattern in file_patterns:
        for fp in glob.glob(pattern, recursive=True):
            if fix_file(fp):
                print(f"  Fixed: {os.path.basename(fp)}")
                fixed += 1
    
    print(f"\nPhase 2 complete: {fixed} files fixed")


if __name__ == '__main__':
    main()
