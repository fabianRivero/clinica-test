import re

filepath = "src/types/admin.ts"
with open(filepath, "r") as f:
    content = f.read()

# Update AdminClientReservationAvailabilityResponse
# Since we only return "operation"
content = re.sub(
    r"export type AdminClientReservationAvailabilityResponse = ClientReservationAvailabilityResponse",
    r"""export type AdminClientReservationAvailabilityResponse = {
  operation: ClientOperationItem
}""",
    content
)

# Update AdminClientFreeMedicalAvailabilityResponse
content = re.sub(
    r"export type AdminClientFreeMedicalAvailabilityResponse = \{\n  client: ClientSnapshot\n  service: \{\n    rawId: number\n    name: string\n  \}\n  calendar: ClientReservationAvailabilityResponse\['calendar'\]\n\}",
    r"""export type AdminClientFreeMedicalAvailabilityResponse = {
  client: ClientSnapshot
  service: {
    rawId: number
    name: string
  }
}""",
    content
)

# Update AdminProspectMedicalAvailabilityResponse
content = re.sub(
    r"export type AdminProspectMedicalAvailabilityResponse = \{\n  prospect: ProspectSnapshot\n  service: \{\n    rawId: number\n    name: string\n  \}\n  calendar: ClientReservationAvailabilityResponse\['calendar'\]\n\}",
    r"""export type AdminProspectMedicalAvailabilityResponse = {
  prospect: ProspectSnapshot
  service: {
    rawId: number
    name: string
  }
}""",
    content
)

with open(filepath, "w") as f:
    f.write(content)

print("Types updated")
