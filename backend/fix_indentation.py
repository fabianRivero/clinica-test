import re

filepath = "config/api_views.py"
with open(filepath, "r") as f:
    content = f.read()

# Fix the dangling parenthesis and order_by indentation
# Specifically for staff_qs assignments
content = re.sub(
    r'\s+\)\s+\)\s+\.order_by\(',
    r'\n        .order_by(',
    content
)

# Second pass for variations
content = re.sub(
    r'\s+\)\s+\.order_by\(',
    r'\n        .order_by(',
    content
)
# Wait, the above might be too broad. 

# Let's target the exact broken blocks
# Block 1 (found around 1680, already fixed but let's be sure)
# Block 2 (around 2937)
content = re.sub(
    r'staff_qs = \(\s+Especialista\.objects\.select_related\("usuario"\)\s+\.prefetch_related\(\s+"especialidades_rel__especialidad",\s+\)\s+\)\s+\.order_by\(',
    r'staff_qs = (\n        Especialista.objects.select_related("usuario")\n        .prefetch_related(\n            "especialidades_rel__especialidad",\n        )\n        .order_by(',
    content,
    flags=re.DOTALL
)

with open(filepath, "w") as f:
    f.write(content)

print("Fixed IndentationError in api_views.py")
