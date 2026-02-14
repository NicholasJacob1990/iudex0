from app.services.ai.skills.pattern_detector import detect_skill_patterns


def test_detect_skill_patterns_identifies_repeated_user_intent():
    prompts = [
        "Preciso analisar peticao inicial trabalhista com foco em preliminares e pedidos.",
        "Quero analisar peticao inicial trabalhista verificando preliminares e pedidos.",
        "Pode analisar peticao inicial trabalhista destacando preliminares e pedidos principais?",
        "Mensagem eventual sem relacao.",
    ]

    patterns = detect_skill_patterns(
        prompts,
        user_id="user-123",
        min_occurrences=3,
        max_patterns=5,
    )

    assert len(patterns) == 1
    candidate = patterns[0]
    assert candidate.user_id == "user-123"
    assert candidate.occurrences == 3
    assert candidate.confidence > 0.5
    assert candidate.suggested_skill_name.startswith("skill-")
    assert len(candidate.suggested_triggers) >= 3


def test_detect_skill_patterns_suggests_jurisprudencia_tool_when_relevant():
    prompts = [
        "Pesquisar jurisprudencia do STJ sobre dano moral em transporte aereo.",
        "Buscar jurisprudencia do STJ para dano moral em atraso de voo.",
        "Encontrar precedente de jurisprudencia no STJ sobre atraso de voo e dano moral.",
    ]

    patterns = detect_skill_patterns(
        prompts,
        user_id="user-abc",
        min_occurrences=2,
        max_patterns=5,
    )

    assert patterns
    assert "search_jurisprudencia" in patterns[0].suggested_tools


def test_detect_skill_patterns_ignores_low_frequency_prompts():
    prompts = [
        "Resumo de um contrato social.",
        "Pergunta pontual sobre prazo recursal.",
    ]

    patterns = detect_skill_patterns(
        prompts,
        user_id="user-x",
        min_occurrences=2,
        max_patterns=5,
    )

    assert patterns == []

