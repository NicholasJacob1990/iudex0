
import sys

file_path = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/services/transcription_service.py"

with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Line indices are 0-based.
# 474 in file is index 473.
# We want to replace line 473 ("            try:\n") with "            if not skip_audit:\n                try:\n"
# And indent lines 474 to 626 (file numbering 475-627) by 4 spaces.

# Verify line 473
if "try:" not in lines[473]:
    print(f"Error: Line 474 (index 473) is not 'try:', it is: {lines[473]}")
    sys.exit(1)

# Verify indentation of 473
current_indent = len(lines[473]) - len(lines[473].lstrip())
if current_indent != 12:
    print(f"Warning: Line 474 indent is {current_indent}, expected 12")

# Replace line 473
lines[473] = " " * 12 + "if not skip_audit:\n" + " " * 16 + "try:\n"

# Indent body (475 to 627 inclusive -> indices 474 to 626)
# But wait, looking at file view:
# 475: from app.services...
# ...
# 627: await emit...
# 628: except...

# So indices 474 to 626 (inclusive) need +4 spaces.
for i in range(474, 627):
    if lines[i].strip(): # Only indent non-empty lines just in case, though python handles empty lines fine usually
        lines[i] = "    " + lines[i]

with open(file_path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("Successfully patched transcription_service.py")
