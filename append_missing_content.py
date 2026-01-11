
import re

def fix_and_append():
    with open('missing_arbitragem_APOSTILA.md', 'r') as f:
        content = f.read()

    # Remove initial headers
    content = re.sub(r'^# missing_arbitragem\n+', '', content)
    content = re.sub(r'^# Prof\. Introdução - Apresentação\n+', '', content)
    content = re.sub(r'^# Fazenda Pública, Arbitragem e Tutela de Evidência\n+', '', content)

    # Fix numbering
    content = content.replace('## 1. ', '## 117. ')
    content = content.replace('## 2. ', '## 118. ')
    content = content.replace('## 3. ', '## 119. ')
    
    # Fix sub-numbering if any (e.g. 2.1 -> 118.1)
    # This is trickier, but let's see if we can do a simple replace for the main ones
    content = content.replace('2.1 ', '118.1 ')
    content = content.replace('2.2 ', '118.2 ')
    content = content.replace('2.3 ', '118.3 ')
    content = content.replace('2.4 ', '118.4 ')
    content = content.replace('2.5 ', '118.5 ')
    content = content.replace('2.5.1 ', '118.5.1 ')
    content = content.replace('2.5.2 ', '118.5.2 ')
    content = content.replace('2.5.3 ', '118.5.3 ')
    content = content.replace('2.6 ', '118.6 ')
    content = content.replace('2.7 ', '118.7 ')
    content = content.replace('2.8 ', '118.8 ')
    content = content.replace('2.9 ', '118.9 ')
    content = content.replace('2.10 ', '118.10 ')
    
    content = content.replace('3.1 ', '119.1 ')
    content = content.replace('3.2 ', '119.2 ')
    content = content.replace('3.3 ', '119.3 ')

    with open('Aulas_PGM_RJ/PROCESSO_CIVIL_CONSOLIDADO_APOSTILA_COMPLETA.md', 'a') as f:
        f.write('\n\n')
        f.write(content)

    print("Content appended successfully.")

if __name__ == '__main__':
    fix_and_append()
