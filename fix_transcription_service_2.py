
import sys

file_path = "/Users/nicholasjacob/Documents/Aplicativos/Iudex/apps/api/app/services/transcription_service.py"

with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Line 825 (index 824) is "            try:\n"
idx_try = 824

if "try:" not in lines[idx_try]:
    print(f"Error: Line 825 (index {idx_try}) is not 'try:', it is: {lines[idx_try]}")
    # Search for try nearby
    for i in range(idx_try-5, idx_try+5):
        if "try:" in lines[i] and len(lines[i].strip()) == 4:
            print(f"Found try at {i+1}: {lines[i]}")
            idx_try = i
            break
    else:
        sys.exit(1)

# Verify indent
current_indent = len(lines[idx_try]) - len(lines[idx_try].lstrip())
if current_indent != 12:
    print(f"Warning: Line {idx_try+1} indent is {current_indent}, expected 12")

# Replace try with if+try
lines[idx_try] = " " * 12 + "if not skip_audit:\n" + " " * 16 + "try:\n"

# Indent body: idx_try+1 to 978 (index 977)
# Check if 979 (index 978) is except
if "except" not in lines[978]: # 979 is index 978
    # adjusting end index logic
    # Find except
    for i in range(idx_try+100, len(lines)):
        if "except Exception as audit_error:" in lines[i]:
            idx_except = i
            break
    else:
        print("Could not find corresponding except block")
        sys.exit(1)
    
    body_end_idx = idx_except - 1
else:
    body_end_idx = 977 # 978 is except

for i in range(idx_try+1, body_end_idx+1):
    if lines[i].strip():
        lines[i] = "    " + lines[i]

with open(file_path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"Successfully patched transcription_service.py (Part 2), try at {idx_try+1}")
