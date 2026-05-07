import re

# Fix PageHeader.tsx
with open("src/components/admin/PageHeader.tsx", "r") as f:
    content = f.read()

content = content.replace("  description: string\n  actions?:", "  description: string\n  children?: React.ReactNode\n  actions?:")
content = content.replace("        <p>{description}</p>\n      </div>", "        <p>{description}</p>\n        {children}\n      </div>")

with open("src/components/admin/PageHeader.tsx", "w") as f:
    f.write(content)

# Fix DataState.tsx
with open("src/components/admin/DataState.tsx", "r") as f:
    content = f.read()

content = content.replace("tone?: 'neutral' | 'danger'", "tone?: 'neutral' | 'warning' | 'danger'")
content = content.replace("      data-state--danger: tone === 'danger',", "      'data-state--danger': tone === 'danger',\n      'data-state--warning': tone === 'warning',")

with open("src/components/admin/DataState.tsx", "w") as f:
    f.write(content)

print("Fixed PageHeader and DataState components")
