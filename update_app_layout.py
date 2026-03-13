import re
with open('/home/bannu/syf_agentic/ui/src/App.tsx', 'r') as f:
    content = f.read()

# Remove main-grid wrapping since we want a single column straight down
content = re.sub(r'<div className="main-grid">.*?<div className="feed">', '<div className="feed" style={{ marginTop: "40px" }}>', content, flags=re.DOTALL)
content = re.sub(r'</div>\s*</div>\s*</main>', '</div></main>', content)

with open('/home/bannu/syf_agentic/ui/src/App.tsx', 'w') as f:
    f.write(content)
