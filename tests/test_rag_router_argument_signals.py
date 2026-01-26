import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))


def test_argumentrag_strong_signal_enables_in_auto_mode():
    from app.services.ai.rag_router import decide_rag_route

    decision = decide_rag_route("Há prova documental do pagamento?", rag_mode="auto")
    assert decision.argument_graph_enabled is True


def test_argumentrag_weak_signal_does_not_enable_in_auto_mode():
    from app.services.ai.rag_router import decide_rag_route

    decision = decide_rag_route("Quem pagou?", rag_mode="auto")
    assert decision.argument_graph_enabled is False


def test_score_signals_distinguishes_weak_vs_strong_argument_signals():
    from app.services.ai.rag_router import score_signals

    strong = score_signals("Há prova documental do pagamento?")
    weak = score_signals("Quem pagou?")

    assert strong["arg_score"] >= 2.0
    assert 0.0 < weak["arg_score"] < 2.0


def test_extract_first_json_object_is_not_greedy():
    from app.services.ai.json_utils import extract_first_json_object

    payload = extract_first_json_object('ok {"sources":["lei"]} trailing {"oops":1}')
    assert payload == {"sources": ["lei"]}

