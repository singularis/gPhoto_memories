import re

css_path = '/home/dante/gPhoto_memories/flask/materials-flask-google-login/static/styles/main.css'
with open(css_path, 'r') as f:
    content = f.read()

# Add --font-scale: 2.0; to :root
if '--font-scale' not in content:
    content = content.replace('--scale:        2.0;', '--scale:        2.0;\n    --font-scale:   2.0;')

# Replace font-size: Xpx; with font-size: calc(Xpx * var(--font-scale));
# Also matches variations like font-size: 15px; font-weight: ... 
def replacer(match):
    size = match.group(1)
    return f"font-size: calc({size}px * var(--font-scale))"

# Only replace pure pixels, ignore calc() if already there
# Regex looks for font-size:\s*(\d+)px
content = re.sub(r'font-size:\s*(\d+)px', replacer, content)

with open(css_path, 'w') as f:
    f.write(content)

print("CSS font sizes updated")
