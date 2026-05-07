import os
import re

filepath = "config/api_views.py"
with open(filepath, "r") as f:
    content = f.read()

# Fix admin_dashboard prefetch
# We look for staff_qs definition and remove the Prefetch(citas_medicas) block
content = re.sub(
    r'staff_qs = \(.*?Especialista\.objects\.select_related\("usuario"\).*?\.prefetch_related\(.*?\n\s+Prefetch\(\n\s+"citas_medicas",.*?\n\s+queryset=CitaMedica\.objects\.select_related\("operacion"\)\.order_by\("fecha_hora"\),.*?\n\s+\),.*?\n\s+\)',
    r'staff_qs = (\n        Especialista.objects.select_related("usuario")\n        .prefetch_related(\n            "especialidades_rel__especialidad",\n        )\n    )',
    content,
    flags=re.DOTALL
)

# Fix other Especialista prefetches
# Target .prefetch_related("especialidades_rel__especialidad", "citas_medicas")
content = content.replace('.prefetch_related("especialidades_rel__especialidad", "citas_medicas")', '.prefetch_related("especialidades_rel__especialidad")')

# Also check for .prefetch_related("citas_medicas", ...) or similar
# Actually, the grep showed:
# line 3039: .prefetch_related("especialidades_rel__especialidad", "citas_medicas")
# line 3099: .prefetch_related("especialidades_rel__especialidad", "citas_medicas")
# line 3135: .prefetch_related("especialidades_rel__especialidad", "citas_medicas")

with open(filepath, "w") as f:
    f.write(content)

print("Fixed Especialista prefetches in api_views.py")
