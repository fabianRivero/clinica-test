import re

filepath = "src/services/api/admin.ts"
with open(filepath, "r") as f:
    content = f.read()

# 1. Update imports
content = content.replace("  CreateAdminTimeSlotPayload,\n", "")
content = content.replace("  UpdateAdminTimeSlotPayload,\n", "")
content = content.replace("  UpdateAdminPaymentStatusResponse,\n}", "  UpdateAdminPaymentStatusResponse,\n  AdminConcurrencyCheckResponse,\n}")

# 2. Replace the slot functions with the new concurrency check
slot_funcs_regex = r"export function createAdminTimeSlot.*?export function deleteAdminTimeSlot.*?}\n"
new_func = """export function checkAdminConcurrency(
  branchId: number,
  startTime: string,
  endTime: string,
  excludeAppointmentId?: number,
) {
  const url = new URL(`${API_BASE_URL}/api/admin/disponibilidad/concurrencia/`)
  url.searchParams.append('sucursal_id', String(branchId))
  url.searchParams.append('hora_inicio', startTime)
  url.searchParams.append('hora_fin', endTime)
  if (excludeAppointmentId) {
    url.searchParams.append('exclude_cita_id', String(excludeAppointmentId))
  }
  return requestJson<AdminConcurrencyCheckResponse>(url.pathname + url.search)
}
"""

content = re.sub(slot_funcs_regex, new_func, content, flags=re.DOTALL)

with open(filepath, "w") as f:
    f.write(content)

print("Done api")
