import os
import re

# Fix config/api_views.py
filepath = "config/api_views.py"
with open(filepath, "r") as f:
    content = f.read()

# Update _staff_item to remove citas_medicas reference
content = content.replace(
    '    citas = list(especialista.citas_medicas.all())',
    '    # Citas ya no se vinculan directamente a especialistas\n    citas = []'
)

# Fix any other remaining .medico references in api_views.py
# (I already fixed _operation_specialist using replace_file_content, 
# but let's be thorough)
content = re.sub(r'upcoming\[0\]\.medico\.usuario', 'upcoming[0].sucursal', content)
content = re.sub(r'citas\[-1\]\.medico\.usuario', 'citas[-1].sucursal', content)

with open(filepath, "w") as f:
    f.write(content)

# Fix config/client_api_views.py
filepath = "config/client_api_views.py"
with open(filepath, "r") as f:
    content = f.read()

# Fix _operation_specialist (if not already fixed)
content = re.sub(
    r'def _operation_specialist\(operacion\):.*?return _full_name\(citas\[-1\]\.medico\.usuario\)',
    '''def _operation_specialist(operacion):
    citas = list(operacion.citas_medicas.all())
    if not citas:
        return "Por asignar"

    now = timezone.now()
    upcoming = [cita for cita in citas if cita.fecha_hora >= now]
    cita = upcoming[0] if upcoming else citas[-1]
    return f"Sede: {cita.sucursal.nombre}"''',
    content,
    flags=re.DOTALL
)

# Fix create/update appointment logic that sets .medico
content = re.sub(r'\n\s+medico=slot\.especialista,', '', content)
content = re.sub(r'\n\s+cita\.medico = slot\.especialista', '', content)
content = content.replace('"medico", ', '')
content = content.replace("'medico', ", "")

with open(filepath, "w") as f:
    f.write(content)

print("Fixed AttributeError and removed old medico references in both view files.")
