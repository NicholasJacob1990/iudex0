"""
Testes para extração/normalização de referências legais (auto_fix_apostilas).

Objetivo: evitar falsos positivos de auditoria de fidelidade por:
- padrões que não capturam leis com ponto (ex: 14.133)
- padrões de julgados que capturam substrings (ex: enunciado -> ado, SMS -> MS)
- "parecer." sem número sendo tratado como julgado
"""

import os
import sys

# Adiciona o diretório raiz do projeto ao path para importar auto_fix_apostilas
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))


def test_extract_legal_references_captures_common_laws_with_dots_and_years():
    from auto_fix_apostilas import extract_legal_references

    text = (
        "O advento da Lei nº 14.133/2021 alterou o regime. "
        "A Lei nº 8.666/1993 ainda aparece em contratos remanescentes. "
        "No âmbito federal, a Lei 9.637/1998 disciplina as OS. "
        "No âmbito municipal, aplica-se a Lei Municipal nº 5.026/2009. "
        "Em concessões, a Lei nº 8.987/1995 é referência."
    )

    refs = extract_legal_references(text)
    assert {"14133", "8666", "9637", "5026", "8987"}.issubset(refs["leis"])


def test_extract_legal_references_avoids_substring_false_positives_for_ado_and_ms():
    from auto_fix_apostilas import extract_legal_references

    text = (
        "O enunciado 49 trata de patrocínio. "
        "Também houve chamamento público SMS 02/2025 na saúde. "
        "Nada disso é ADO ou MS (como processos judiciais)."
    )

    refs = extract_legal_references(text)

    # Não deve extrair 'ado 49' de 'enunciado 49' e nem 'ms 02' de 'SMS 02/2025'
    assert not any(j.startswith("ado") for j in refs["julgados"])
    assert not any(j.startswith("ms") for j in refs["julgados"])


def test_extract_legal_references_parecer_requires_number():
    from auto_fix_apostilas import extract_legal_references

    # 'parecer.' não deve ser classificado como julgado
    refs_noise = extract_legal_references("Observado esse direcionamento aqui dado pelo parecer.")
    assert not any("parecer" in j for j in refs_noise["julgados"])

    # Com número, deve ser capturado
    refs_ok = extract_legal_references("Parecer PG SUBCONS nº 11/2023 publicado em revista.")
    assert any(j.startswith("parecer") for j in refs_ok["julgados"])

