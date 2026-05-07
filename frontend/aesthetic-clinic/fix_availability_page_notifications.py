import re

filepath = "src/pages/admin/AdminAvailabilityPage.tsx"
with open(filepath, "r") as f:
    content = f.read()

# Fix showNotification syntax
content = re.sub(r"showNotification\(\{ title: 'Exito', message: 'Exito', (.*?), tone: 'success' \}\)", r"showNotification({ title: 'Exito', message: \1, tone: 'success' })", content)
content = re.sub(r"showNotification\(\{ title: 'Error', message: 'Validacion', (.*?), tone: 'danger' \}\)", r"showNotification({ title: 'Error', message: \1, tone: 'danger' })", content)
content = re.sub(r"showNotification\(\{ title: 'Error', message: 'Error', err\.message, tone: 'danger' \}\)", r"showNotification({ title: 'Error', message: err.message, tone: 'danger' })", content)
content = re.sub(r"showNotification\(\{ title: 'Exito', message: 'Agenda eliminada', (.*?), tone: 'success' \}\)", r"showNotification({ title: 'Agenda eliminada', message: \1, tone: 'success' })", content)
content = re.sub(r"showNotification\(\{ title: 'Error', message: 'Error al eliminar', err\.message, tone: 'danger' \}\)", r"showNotification({ title: 'Error al eliminar', message: err.message, tone: 'danger' })", content)
content = re.sub(r"showNotification\(\{ title: 'Exito', message: 'Excepcion eliminada', (.*?), tone: 'success' \}\)", r"showNotification({ title: 'Excepcion eliminada', message: 'La excepcion fue borrada exitosamente', tone: 'success' })", content)

with open(filepath, "w") as f:
    f.write(content)

print("Fixed AdminAvailabilityPage notifications")
