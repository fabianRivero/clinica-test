filepath = "config/api_views.py"
with open(filepath, "r") as f:
    content = f.read()

# Remove DisponibilidadCita from import
content = content.replace("    DisponibilidadCita,\n", "")
content = content.replace(", DisponibilidadCita", "")

# We don't have to remove all its logic right now because python only evaluates function bodies when called,
# EXCEPT there might be a problem if it's evaluated at module level. Let's see if it compiles.
with open(filepath, "w") as f:
    f.write(content)

print("Done")
