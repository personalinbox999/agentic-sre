import re

with open('/home/bannu/syf_agentic/ui/src/App.tsx', 'r') as f:
    content = f.read()

# Instead of the sidebar + feed grid, stack them in a single column
# Replace `<div className="main-grid">` with just a plain `<div>`
content = content.replace('<div className="main-grid">', '<div className="main-grid" style={{ display: "flex", flexDirection: "column", gap: "24px" }}>')

with open('/home/bannu/syf_agentic/ui/src/App.tsx', 'w') as f:
    f.write(content)

