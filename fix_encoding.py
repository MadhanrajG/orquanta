#!/usr/bin/env python3
"""Fix mojibake and special Unicode characters across the OrQuanta codebase.

Replaces em-dashes, arrows, smart quotes, bullets, and other non-ASCII
characters with their ASCII equivalents for international compatibility.
"""
import os
import re
import glob

REPLACEMENTS = [
    # Mojibake patterns (UTF-8 bytes decoded as Windows-1252)
    ('\u00c3\u00a2\u00e2\u201a\u00ac\u00e2\u20ac\u0153', '-'),  # en-dash mojibake
    ('\u00c3\u00a2\u00e2\u201a\u00ac\u00e2\u20ac\u201c', '-'),  # em-dash mojibake

    # Em-dash and en-dash -> ASCII hyphen
    ('\u2014', ' - '),   # em-dash
    ('\u2013', '-'),      # en-dash

    # Arrows -> ASCII
    ('\u2192', '->'),     # right arrow
    ('\u2190', '<-'),     # left arrow
    ('\u2191', '^'),      # up arrow
    ('\u2193', 'v'),      # down arrow

    # Middle dot / bullet -> hyphen
    ('\u00b7', ' - '),    # middle dot
    ('\u2022', '-'),      # bullet

    # Smart quotes -> straight quotes
    ('\u201c', '"'),      # left double quote
    ('\u201d', '"'),      # right double quote
    ('\u2018', "'"),      # left single quote
    ('\u2019', "'"),      # right single quote

    # Ellipsis
    ('\u2026', '...'),    # horizontal ellipsis

    # Multiplication sign
    ('\u00d7', 'x'),      # multiplication sign

    # Box drawing / decorative lines
    ('\u2500', '-'),      # box drawing horizontal
    ('\u2501', '-'),      # box drawing heavy horizontal
    ('\u2550', '='),      # box drawing double horizontal
    ('\u2503', '|'),      # box drawing heavy vertical

    # Stars/decorative
    ('\u2605', '*'),      # black star
    ('\u25cf', '*'),      # black circle
    ('\u25cb', 'o'),      # white circle
    ('\u25c6', '*'),      # black diamond
    ('\u25b8', '>'),      # black right-pointing small triangle
    ('\u25b9', '>'),      # white right-pointing small triangle
    ('\u25aa', '-'),      # black small square

    # Copyright
    ('\u00a9', '(c)'),    # copyright sign
]

# Emoji to remove or replace with text
EMOJI_REPLACEMENTS = [
    ('\U0001f680', ''),      # rocket
    ('\u2705', ''),          # white check mark
    ('\u274c', ''),          # cross mark
    ('\u26a0\ufe0f', ''),    # warning
    ('\u26a0', ''),          # warning (no variation)
    ('\U0001f4a1', ''),      # light bulb
    ('\U0001f525', ''),      # fire
    ('\U0001f3af', ''),      # target
    ('\U0001f4b0', ''),      # money bag
    ('\U0001f916', ''),      # robot
    ('\u26a1', ''),          # zap
    ('\U0001f310', ''),      # globe
    ('\U0001f4ca', ''),      # bar chart
    ('\U0001f511', ''),      # key
    ('\U0001f6e1', ''),      # shield
    ('\U0001f6e1\ufe0f', ''),# shield + variation
    ('\U0001f389', ''),      # party popper
    ('\u2728', ''),          # sparkles
    ('\U0001f48e', ''),      # gem
    ('\U0001f6a8', ''),      # rotating light
    ('\U0001f504', ''),      # counterclockwise arrows
    ('\U0001f4c8', ''),      # chart increasing
    ('\U0001f4b8', ''),      # money with wings
    ('\U0001f3c6', ''),      # trophy
    ('\u2b50', ''),          # star
    ('\U0001f31f', ''),      # glowing star
    ('\U0001f527', ''),      # wrench
    ('\U0001f4dd', ''),      # memo
    ('\U0001f5a5', ''),      # desktop computer
    ('\U0001f9e0', ''),      # brain
    ('\u2699\ufe0f', ''),    # gear
    ('\u2699', ''),          # gear
    ('\U0001f512', ''),      # lock
    ('\U0001f4e1', ''),      # satellite antenna
    ('\U0001f30d', ''),      # earth globe
    ('\U0001f3a8', ''),      # palette
    ('\U0001f4e6', ''),      # package
    ('\U0001f4bb', ''),      # laptop
    ('\U0001f30a', ''),      # water wave
    ('\U0001f9be', ''),      # mechanical arm
    ('\U0001f4c5', ''),      # calendar
    ('\U0001f41b', ''),      # bug
    ('\u23f3', ''),          # hourglass
    ('\U0001f50c', ''),      # electric plug
    ('\u2601\ufe0f', ''),    # cloud
    ('\u2601', ''),          # cloud
    ('\u2b06', ''),          # up arrow emoji
    ('\U0001f510', ''),      # closed lock with key
    ('\U0001f52e', ''),      # crystal ball
    ('\U0001f441', ''),      # eye
    ('\U0001f4cb', ''),      # clipboard
    ('\U0001f9f9', ''),      # broom
    ('\U0001f9ea', ''),      # test tube
    ('\U0001f550', ''),      # clock
    ('\u267b\ufe0f', ''),    # recycling symbol
    ('\u267b', ''),          # recycling symbol
    ('\u2764', ''),          # red heart
    ('\U0001f331', ''),      # seedling
    ('\U0001f4c9', ''),      # chart decreasing
    ('\U0001f44b', ''),      # waving hand
    ('\U0001f91d', ''),      # handshake
    ('\U0001f4aa', ''),      # flexed biceps
    ('\U0001f3d7', ''),      # building construction
    ('\U0001fa84', ''),      # magic wand
    ('\U0001f4cc', ''),      # pushpin
    ('\U0001f50d', ''),      # magnifying glass
    ('\U0001f3f7', ''),      # label
]

def fix_file(filepath):
    """Fix encoding issues in a single file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                content = f.read()
        except:
            print(f"  SKIP (cannot decode): {filepath}")
            return False

    original = content

    # Apply character replacements
    for old, new in REPLACEMENTS:
        content = content.replace(old, new)

    # Apply emoji replacements
    for old, new in EMOJI_REPLACEMENTS:
        content = content.replace(old, new)

    # Clean up double spaces from removals
    while '  ' in content and '  ' not in original:
        content = content.replace('  ', ' ')

    if content != original:
        with open(filepath, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
        return True
    return False


def main():
    # Frontend JSX/JS/CSS
    patterns = [
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

    fixed_count = 0
    for pattern in patterns:
        for filepath in glob.glob(pattern, recursive=True):
            if fix_file(filepath):
                print(f"  Fixed: {os.path.basename(filepath)}")
                fixed_count += 1

    print(f"\nTotal files fixed: {fixed_count}")


if __name__ == '__main__':
    main()
