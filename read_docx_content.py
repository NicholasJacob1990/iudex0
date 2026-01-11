import sys
from docx import Document
import os

def read_docx(file_path):
    try:
        doc = Document(file_path)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return '\n'.join(full_text)
    except Exception as e:
        return f"Error reading docx: {e}"

if __name__ == "__main__":
    file_path = "Aulas_PGM_RJ/Precessocivilraw.txt"
    content = read_docx(file_path)
    print(f"Total characters: {len(content)}")
    print("Last 5000 characters:")
    print(content[-5000:])
