import re

filepath = "src/services/api/admin.ts"
with open(filepath, "r") as f:
    content = f.read()

# Update createAdminClientReservation
content = re.sub(
    r"export function createAdminClientReservation\(clientId: number, operationId: number, slotId: number\) \{\n  return requestJsonWithBody<CreateAdminClientReservationResponse>\([\s\S]*?\n  \)\n\}",
    r"""export function createAdminClientReservation(clientId: number, operationId: number, data: { branchId: number, dateTime: string }) {
  return requestJsonWithBody<CreateAdminClientReservationResponse>(
    `/api/admin/clientes/${clientId}/operaciones/${operationId}/reservar/`,
    data,
  )
}""",
    content
)

# Update createAdminClientFreeMedicalAppointment
content = re.sub(
    r"export function createAdminClientFreeMedicalAppointment\(clientId: number, slotId: number\) \{\n  return requestJsonWithBody<CreateAdminClientFreeMedicalAppointmentResponse>\([\s\S]*?\n  \)\n\}",
    r"""export function createAdminClientFreeMedicalAppointment(clientId: number, data: { branchId: number, dateTime: string }) {
  return requestJsonWithBody<CreateAdminClientFreeMedicalAppointmentResponse>(
    `/api/admin/clientes/${clientId}/cita-medica/reservar/`,
    data,
  )
}""",
    content
)

# Update createAdminProspectMedicalAppointment
content = re.sub(
    r"export function createAdminProspectMedicalAppointment\(prospectId: number, slotId: number\) \{\n  return requestJsonWithBody<CreateAdminProspectMedicalAppointmentResponse>\([\s\S]*?\n  \)\n\}",
    r"""export function createAdminProspectMedicalAppointment(prospectId: number, data: { branchId: number, dateTime: string }) {
  return requestJsonWithBody<CreateAdminProspectMedicalAppointmentResponse>(
    `/api/admin/prospectos/${prospectId}/cita-medica/reservar/`,
    data,
  )
}""",
    content
)

with open(filepath, "w") as f:
    f.write(content)

print("admin.ts reservation methods updated")
