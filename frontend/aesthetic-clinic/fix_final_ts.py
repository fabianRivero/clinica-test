import re

# Fix PageHeader.tsx
with open("src/components/admin/PageHeader.tsx", "r") as f:
    content = f.read()

content = content.replace("  description,\n  actions,\n}: PageHeaderProps)", "  description,\n  children,\n  actions,\n}: PageHeaderProps)")

with open("src/components/admin/PageHeader.tsx", "w") as f:
    f.write(content)

# Fix AdminAvailabilityPage.tsx unused imports
with open("src/pages/admin/AdminAvailabilityPage.tsx", "r") as f:
    content = f.read()

content = re.sub(r"import type \{\n  AdminHabitualSchedule,\n  AdminSpecialistAvailabilityException,\n\} from '\.\./\.\./types/admin'\n", "", content)

with open("src/pages/admin/AdminAvailabilityPage.tsx", "w") as f:
    f.write(content)

# Fix AdminClientDetailPage.tsx unused imports
with open("src/pages/admin/AdminClientDetailPage.tsx", "r") as f:
    content = f.read()

content = content.replace("import { useCallback, useEffect, useMemo, useState } from 'react'", "import { useCallback, useState } from 'react'")
content = content.replace("  getAdminClientFreeMedicalAvailability,\n", "")
content = content.replace("  getAdminClientReservationAvailability,\n", "")
content = content.replace("  AdminClientFreeMedicalAvailabilityResponse,\n", "")
content = content.replace("  AdminClientReservationAvailabilityResponse,\n", "")

with open("src/pages/admin/AdminClientDetailPage.tsx", "w") as f:
    f.write(content)

print("Fixed all remaining TS errors")
