import sys

# Patch App.jsx
with open('v4/frontend/src/App.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add VeroControl import
if 'VeroControl' not in content:
    old_import = 'import AgentMonitor from'
    new_import = 'import VeroControl from "./pages/VeroControl.jsx"\nimport AgentMonitor from'
    content = content.replace(old_import, new_import, 1)
    print("Added VeroControl import")

# 2. Add Vero nav item before settings
if "to: '/vero'" not in content and 'to: "/vero"' not in content:
    for old_nav in ["{ to: '/settings'", '{ to: "/settings"']:
        if old_nav in content:
            new_nav = "{ to: '/vero', icon: '\U0001f451', label: 'Vero' },\n    " + old_nav
            content = content.replace(old_nav, new_nav, 1)
            print("Added Vero nav item")
            break

# 3. Add Route for /vero
if 'VeroControl' not in content or '/vero' not in content:
    for agents_route in ["path='/agents'", 'path="/agents"']:
        if agents_route in content:
            idx = content.find(agents_route)
            close_idx = content.find('/>', idx) + 2
            content = content[:close_idx] + '\n                <Route path="/vero" element={<VeroControl />} />' + content[close_idx:]
            print("Added Vero route")
            break

with open('v4/frontend/src/App.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("App.jsx patch complete")
print("VeroControl import:", 'VeroControl' in content)
print("Vero nav:", '/vero' in content)
