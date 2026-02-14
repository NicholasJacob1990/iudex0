"""Shared test fixtures."""

import pytest


@pytest.fixture
def sample_legislacao_text():
    return (
        "Art. 150. Sem prejuízo de outras garantias asseguradas ao contribuinte, "
        "é vedado à União, aos Estados, ao Distrito Federal e aos Municípios:\n"
        "I - exigir ou aumentar tributo sem lei que o estabeleça;\n"
        "II - instituir tratamento desigual entre contribuintes que se encontrem "
        "em situação equivalente;\n"
        "§ 1º A vedação do inciso III, b, não se aplica aos tributos previstos "
        "nos arts. 148, I, 153, I, II, IV e V; e 154, II.\n"
        "§ 4º As vedações expressas no inciso VI, alíneas b e c, compreendem "
        "somente o patrimônio, a renda e os serviços, relacionados com as "
        "finalidades essenciais das entidades nelas mencionadas.\n\n"
        "Art. 151. É vedado à União:\n"
        "I - instituir tributo que não seja uniforme em todo o território nacional;\n"
    )


@pytest.fixture
def sample_jurisprudencia_text():
    return (
        "EMENTA: RECURSO EXTRAORDINÁRIO. DIREITO TRIBUTÁRIO. ICMS. "
        "EXCLUSÃO DA BASE DE CÁLCULO DO PIS E DA COFINS.\n"
        "O ICMS não compõe a base de cálculo para a incidência do PIS e da COFINS.\n"
        "Decisão: O Tribunal, por maioria, apreciando o Tema 69 da repercussão geral, "
        "negou provimento ao recurso extraordinário, nos termos do Art. 150, § 1º do CTN "
        "e conforme Art. 195, inc. I, al. b da CF.\n"
        "RE 574706. Relator Min. Cármen Lúcia. STF.\n"
        "Súmula 435 do STJ também foi citada como precedente.\n"
    )


@pytest.fixture
def sample_metadata():
    return {
        "title": "Aula 15 - Direito Tributário",
        "source_type": "transcricao",
        "jurisdiction": "federal",
    }
