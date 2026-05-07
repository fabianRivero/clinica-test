import re

filepath = "config/client_api_views.py"
with open(filepath, "r") as f:
    content = f.read()

# Replace _build_operation_slot_map with a dummy
dummy_map = """def _build_operation_slot_map(operacion, editing_appointment=None):
    return {
        "windowStart": None,
        "windowEnd": None,
        "monthLabel": "",
        "availableDates": [],
        "slotsByDate": {},
        "slotCount": 0,
    }"""

content = re.sub(r'def _build_operation_slot_map\(operacion, editing_appointment=None\):.*?(?=\ndef _get_client_operation)', dummy_map, content, flags=re.DOTALL)

with open(filepath, "w") as f:
    f.write(content)

print("Done")
