import re

filepath = "src/services/api/admin.ts"
with open(filepath, "r") as f:
    content = f.read()

# Replace checkAdminConcurrency
content = re.sub(
    r"export function checkAdminConcurrency\([\s\S]*?return requestJson<AdminConcurrencyCheckResponse>\(url.pathname \+ url.search\)\n\}",
    r"""export function checkAdminConcurrency(
  branchId: number,
  date: string,
  startTime: string,
  endTime: string,
) {
  return requestJsonWithBody<AdminConcurrencyCheckResponse>(
    '/api/admin/disponibilidad/concurrencia/',
    {
      sucursal_id: branchId,
      fecha: date,
      hora_inicio: startTime,
      hora_fin: endTime,
    }
  )
}""",
    content
)

with open(filepath, "w") as f:
    f.write(content)

print("admin.ts checkAdminConcurrency updated")
