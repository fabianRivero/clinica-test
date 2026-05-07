import os
import re

# 1. Update config/api_urls.py to remove admin_availability routes
filepath = "config/api_urls.py"
with open(filepath, "r") as f:
    content = f.read()

# Remove imports from admin_availability_views
content = re.sub(r'from config.admin_availability_views import \([^)]+\)\n', '', content, flags=re.DOTALL)

# Remove all routes starting with "disponibilidad/"
lines = content.split('\n')
new_lines = []
for line in lines:
    if 'path("disponibilidad/' not in line and 'admin_availability' not in line:
        new_lines.append(line)
content = '\n'.join(new_lines)

with open(filepath, "w") as f:
    f.write(content)

# 2. Update config/client_api_views.py to remove old availability routes that use DisponibilidadCita
filepath = "config/client_api_views.py"
with open(filepath, "r") as f:
    content = f.read()

content = content.replace("from operations.models import CitaMedica, CitaClienteLibre, DisponibilidadCita", "from operations.models import CitaMedica, CitaClienteLibre")
with open(filepath, "w") as f:
    f.write(content)

# 3. Completely replace admin_availability_views.py to avoid compile errors
filepath = "config/admin_availability_views.py"
with open(filepath, "w") as f:
    f.write("# TODO: Reimplement for open agenda\nfrom django.http import JsonResponse\n\ndef dummy_view(request):\n    return JsonResponse({})")

# 4. Wipe operations/scheduling.py for now
filepath = "operations/scheduling.py"
with open(filepath, "w") as f:
    f.write("# TODO: Implement presence scheduling\nBLOCKING_RESERVATION_STATES = []\ndef check_availability(*args, **kwargs):\n    pass\n")

print("Done")
