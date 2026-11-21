#!/usr/bin/env python3
help_p = open(r'c:\ai-gpu-cloud\v4\frontend\src\pages\HelpPage.jsx', encoding='utf-8').read()
old = "            {\n                q: 'What is OrQuanta?',"
new = """            {
                q: 'How do I reset my password?',
                a: 'Click Forgot password? on the Sign In page, enter your email, and check your inbox for a reset link. The link expires in 1 hour. If you do not receive it check spam or contact support@orquanta.com.'
            },
            {
                q: 'What is OrQuanta?',"""
if old in help_p:
    help_p = help_p.replace(old, new, 1)
    open(r'c:\ai-gpu-cloud\v4\frontend\src\pages\HelpPage.jsx', 'w', encoding='utf-8').write(help_p)
    print('SUCCESS')
else:
    print('WARN: anchor not found — first 5 chars:', repr(help_p[help_p.find('What is OrQuanta')-30:help_p.find('What is OrQuanta')+50]))
