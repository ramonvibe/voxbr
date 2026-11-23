from evals.runner import check


def test_expected_transfer_happened():
    ok, problems = check({"expect": {"transfer": True, "reason": "customer_request"}},
                         [{"reason": "customer_request"}], None)
    assert ok and not problems


def test_missing_and_unexpected_transfer():
    assert check({"expect": {"transfer": True}}, [], None) == (False, ["esperava transbordo"])
    assert check({"expect": {"transfer": False}}, [{"reason": "no_answer"}], None) == (False, ["transbordou sem precisar"])


def test_wrong_reason_and_judge_failure():
    ok, problems = check({"expect": {"transfer": True, "reason": "customer_request"}}, [{"reason": "no_answer"}], False)
    assert not ok
    assert problems == ["motivo no_answer != customer_request", "juiz reprovou a resposta"]


def test_no_expectations_passes():
    assert check({}, [], None) == (True, [])


def test_knowledge_message_keeps_only_relevant_chunks():
    from apps.agent.main import knowledge_message

    msg = knowledge_message([("preço da limpeza: R$ 180", 0.7), ("endereço", 0.2)], min_score=0.35)
    assert "R$ 180" in msg and "endereço" not in msg
    empty = knowledge_message([("endereço", 0.2)], min_score=0.35)
    assert "nada relevante" in empty and "transfer_to_human" in empty


def test_inline_knowledge_only_for_small_ready_bases():
    from core import rag
    from core.db import AgentProfile, Document, SessionLocal

    with SessionLocal() as db:
        agent = AgentProfile(name="a", rules_md="")
        db.add(agent)
        db.flush()
        db.add_all([Document(agent_id=agent.id, name="precos.pdf", source="file", content="Limpeza: R$ 180", status="ready"),
                    Document(agent_id=agent.id, name="x", source="file", content="rascunho", status="error")])
        db.commit()
        text = rag.inline_knowledge(agent)
        assert "## precos.pdf" in text and "R$ 180" in text and "rascunho" not in text
        assert rag.inline_knowledge(agent, max_chars=10) is None
