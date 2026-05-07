import re

filepath = "src/pages/admin/AdminAvailabilityPage.tsx"
with open(filepath, "r") as f:
    content = f.read()

# Fix the last remaining errors
content = re.sub(r"showNotification\(\{ title: '(.*?)', message: '(.*?)', res\.detail, tone: '(.*?)' \}\)", r"showNotification({ title: '\1', message: res.detail, tone: '\3' })", content)
content = re.sub(r"showNotification\(\{ title: '(.*?)', message: '(.*?)', err\.message, tone: '(.*?)' \}\)", r"showNotification({ title: '\1', message: err.message, tone: '\3' })", content)

with open(filepath, "w") as f:
    f.write(content)

print("Fixed AdminAvailabilityPage notifications again")
