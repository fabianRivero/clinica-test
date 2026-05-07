import re

def remove_unused(filepath):
    with open(filepath, "r") as f:
        content = f.read()

    patterns = [
        r"const WEEKDAY_LABELS = \['Lun', 'Mar', 'Mie', 'Jue', 'Vie', 'Sab', 'Dom'\]",
        r"function toDateKey\(value: Date\) \{[\s\S]*?\}",
        r"function monthStart\(value: Date\) \{[\s\S]*?\}",
        r"function addMonths\(value: Date, amount: number\) \{[\s\S]*?\}",
        r"function buildCalendarGrid\(monthValue: Date\) \{[\s\S]*?\}",
        r"function monthLabel\(value: Date\) \{[\s\S]*?\}",
        r"function longDateLabel\(value: string\) \{[\s\S]*?\}"
    ]

    for p in patterns:
        content = re.sub(p, "", content, flags=re.DOTALL)

    with open(filepath, "w") as f:
        f.write(content)

remove_unused("src/pages/admin/AdminClientDetailPage.tsx")
remove_unused("src/pages/admin/AdminProspectsPage.tsx")

# Fix types in admin.ts
with open("src/types/admin.ts", "r") as f:
    types = f.read()

types = re.sub(r"operation: ClientOperationItem", "operation: ClientOperation", types)
types += "\n\nexport type AdminBranch = {\n  id: number\n  nombre: string\n  es_principal: boolean\n}\n"

with open("src/types/admin.ts", "w") as f:
    f.write(types)

# Also fix imports in src/services/api/admin.ts
with open("src/services/api/admin.ts", "r") as f:
    api = f.read()

if "AdminBranch" not in api[:500]:
    api = re.sub(r"AdminAvailabilityResponse,", "AdminAvailabilityResponse,\n  AdminBranch,", api)
    with open("src/services/api/admin.ts", "w") as f:
        f.write(api)

print("Fixed TS errors")
