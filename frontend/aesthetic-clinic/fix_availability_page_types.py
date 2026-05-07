import re

filepath = "src/pages/admin/AdminAvailabilityPage.tsx"
with open(filepath, "r") as f:
    content = f.read()

# Fix useApiResource reload
content = re.sub(r"const \{ data, isLoading, error, refetch \} = useApiResource\(getAdminAvailability\)", "const { data, isLoading, error, reload } = useApiResource(getAdminAvailability)", content)
content = re.sub(r"refetch\(\)", "reload()", content)

# Fix useNotifications
content = re.sub(r"const \{ notifySuccess, notifyError \} = useNotifications\(\)", "const { showNotification } = useNotifications()", content)
content = re.sub(r"notifySuccess\((.*?)\)", r"showNotification({ title: 'Exito', message: \1, tone: 'success' })", content)
content = re.sub(r"notifyError\((.*?)\)", r"showNotification({ title: 'Error', message: \1, tone: 'danger' })", content)

with open(filepath, "w") as f:
    f.write(content)

print("Fixed AdminAvailabilityPage errors")
