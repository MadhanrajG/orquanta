import sys

# Patch Dashboard.jsx to add VeroStatus widget
with open('v4/frontend/src/pages/Dashboard.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

if 'VeroStatus' not in content:
    # Add import
    first_import = content.find('import ')
    content = 'import VeroStatus from "../components/VeroStatus.jsx"\n' + content

    # Add VeroStatus at the top of the returned JSX
    # Find the first div or fragment after "return ("
    return_idx = content.find('return (')
    if return_idx == -1:
        return_idx = content.find('return(')
    # Find the first opening tag after return (
    open_tag_idx = content.find('<', return_idx) + 1
    # Find closing of that tag  
    close_tag_idx = content.find('>', open_tag_idx) + 1
    # Insert VeroStatus right after the outer div opening
    content = content[:close_tag_idx] + '\n      <VeroStatus />' + content[close_tag_idx:]
    print("VeroStatus inserted into Dashboard")
else:
    print("VeroStatus already in Dashboard")

with open('v4/frontend/src/pages/Dashboard.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Dashboard.jsx patch complete")
print("VeroStatus present:", 'VeroStatus' in open('v4/frontend/src/pages/Dashboard.jsx', encoding='utf-8').read())
