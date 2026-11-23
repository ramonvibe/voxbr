import pytest
from fastapi.testclient import TestClient

from core import db as coredb
from tests.conftest import PASSWORD

AGENT_BODY = {
    "name": "Ag", "greeting": "Oi", "recording_notice": "Gravada",
    "stt": [{"vendor": "openai", "model": "m"}], "llm": [{"vendor": "openai", "model": "m"}],
    "tts": [{"vendor": "openai", "model": "m"}], "embedding": {"vendor": "openai", "model": "e"},
}


# ---------- auth ----------


def test_login_ok_sets_cookie_and_me(make_user, client):
    make_user("a@test.com", role="admin")
    r = client.post("/api/auth/login", json={"email": " A@Test.com ", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert "httponly" in r.headers["set-cookie"].lower()
    assert client.get("/api/auth/me").json()["email"] == "a@test.com"


def test_login_wrong_password(make_user, client):
    make_user("a@test.com")
    assert client.post("/api/auth/login", json={"email": "a@test.com", "password": "x"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "no@test.com", "password": "x"}).status_code == 401


def test_login_inactive(make_user, client):
    make_user("a@test.com", active=False)
    assert client.post("/api/auth/login", json={"email": "a@test.com", "password": PASSWORD}).status_code == 401


def test_me_without_cookie_and_garbage_cookie(client):
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.set("voxbr_session", "lixo")
    assert client.get("/api/auth/me").status_code == 401


def test_deactivated_user_loses_session(make_user, login, db):
    u = make_user("a@test.com")
    c = login("a@test.com")
    u.active = False
    db.commit()
    assert c.get("/api/auth/me").status_code == 401


def test_logout_clears_cookie(make_user, login):
    make_user("a@test.com")
    c = login("a@test.com")
    assert c.post("/api/auth/logout").json() == {"ok": True}
    assert c.get("/api/auth/me").status_code == 401


def test_startup_bootstrap_creates_admin_and_agent(app_client, db):
    with TestClient(app_client) as c:
        assert c.post("/api/auth/login", json={"email": "boot@test.com", "password": "bootpass123"}).status_code == 200
        assert len(c.get("/api/agents").json()) == 1


# ---------- permissões ----------


@pytest.mark.parametrize("method,path", [
    ("get", "/api/agents"), ("get", "/api/numbers"), ("get", "/api/queues"),
    ("get", "/api/users"), ("get", "/api/calls"), ("post", "/api/test-call"),
])
def test_attendant_forbidden_on_admin_endpoints(make_user, login, method, path):
    make_user("t@test.com")
    c = login("t@test.com")
    assert getattr(c, method)(path, **({"json": {}} if method == "post" else {})).status_code == 403


def test_anonymous_gets_401(client):
    for p in ("/api/agents", "/api/console", "/api/messages", "/api/catalog"):
        assert client.get(p).status_code == 401


def test_attendant_can_use_console_and_messages(make_user, login):
    make_user("t@test.com")
    c = login("t@test.com")
    assert c.get("/api/console").json() == {"waiting": [], "active": []}
    assert c.get("/api/messages").json() == []
    assert c.get("/api/catalog").status_code == 200


# ---------- números ----------


def number_body(**kw):
    return {"did": "+55 (31) 99999-0000", "mode": "ai", **kw}


def test_number_did_normalized(admin, make_agent):
    a = make_agent()
    r = admin.post("/api/numbers", json=number_body(agent_id=a.id))
    assert r.status_code == 201 and r.json()["did"] == "+5531999990000"
    assert r.json()["agent_name"] == "Agente"


def test_number_ai_without_agent_422(admin):
    assert admin.post("/api/numbers", json=number_body()).status_code == 422


def test_number_human_direct_without_queue_422(admin):
    assert admin.post("/api/numbers", json=number_body(mode="human_direct")).status_code == 422


def test_number_human_direct_ok(admin, make_queue):
    q = make_queue()
    r = admin.post("/api/numbers", json=number_body(mode="human_direct", queue_id=q.id))
    assert r.status_code == 201 and r.json()["queue_name"] == "Fila"


def test_number_duplicate_409(admin, make_agent):
    a = make_agent()
    assert admin.post("/api/numbers", json=number_body(agent_id=a.id)).status_code == 201
    r = admin.post("/api/numbers", json=number_body(did="5531999990000", agent_id=a.id))
    assert r.status_code == 409


def test_number_update_and_delete(admin, make_agent):
    a = make_agent()
    n = admin.post("/api/numbers", json=number_body(agent_id=a.id)).json()
    r = admin.put(f"/api/numbers/{n['id']}", json=number_body(agent_id=a.id, label="X"))
    assert r.status_code == 200 and r.json()["label"] == "X"
    assert admin.delete(f"/api/numbers/{n['id']}").status_code == 204
    assert admin.put(f"/api/numbers/{n['id']}", json=number_body(agent_id=a.id)).status_code == 404


# ---------- filas ----------


def test_queue_member_ids_saved(admin, make_user):
    u = make_user("m@test.com")
    r = admin.post("/api/queues", json={"name": "Vendas", "member_ids": [u.id],
                                         "hours": {"tz": "America/Sao_Paulo", "days": {"mon": [["08:00", "18:00"]]}}})
    assert r.status_code == 201 and r.json()["member_ids"] == [u.id]
    qid = r.json()["id"]
    assert admin.get("/api/users").json()[1]["queue_ids"] == [qid] or any(
        x["queue_ids"] == [qid] for x in admin.get("/api/users").json())
    r = admin.put(f"/api/queues/{qid}", json={"name": "Vendas2", "member_ids": []})
    assert r.json()["member_ids"] == [] and r.json()["name"] == "Vendas2"


@pytest.mark.parametrize("hours", [
    {"days": {"mon": [["18:00", "08:00"]]}},
    {"days": {"mon": [["08:00", "08:00"]]}},
    {"days": {"xxx": [["08:00", "18:00"]]}},
    {"days": {"mon": [["8h", "18h"]]}},
])
def test_queue_invalid_hours_422(admin, hours):
    assert admin.post("/api/queues", json={"name": "Q", "hours": hours}).status_code == 422


def test_queue_delete(admin, make_queue):
    q = make_queue()
    assert admin.delete(f"/api/queues/{q.id}").status_code == 204


# ---------- usuários ----------


def user_body(**kw):
    return {"email": "New@Test.com", "name": "Novo", "password": "12345678", **kw}


def test_user_create_requires_password(admin):
    assert admin.post("/api/users", json=user_body(password=None)).status_code == 422
    assert admin.post("/api/users", json=user_body(password="curta")).status_code == 422


def test_user_create_ok_and_login(admin, client):
    r = admin.post("/api/users", json=user_body())
    assert r.status_code == 201 and r.json()["email"] == "new@test.com"
    assert client.post("/api/auth/login", json={"email": "new@test.com", "password": "12345678"}).status_code == 200


def test_user_duplicate_email_409(admin):
    assert admin.post("/api/users", json=user_body()).status_code == 201
    assert admin.post("/api/users", json=user_body(email="new@test.com")).status_code == 409


def test_user_update_keeps_password_when_omitted(admin, client):
    uid = admin.post("/api/users", json=user_body()).json()["id"]
    assert admin.put(f"/api/users/{uid}", json=user_body(password=None, name="Outro")).status_code == 200
    assert client.post("/api/auth/login", json={"email": "new@test.com", "password": "12345678"}).status_code == 200


def test_admin_cannot_demote_deactivate_delete_self(admin):
    me = admin.get("/api/auth/me").json()
    base = {"email": me["email"], "name": me["name"]}
    assert admin.put(f"/api/users/{me['id']}", json={**base, "role": "attendant"}).status_code == 409
    assert admin.put(f"/api/users/{me['id']}", json={**base, "role": "admin", "active": False}).status_code == 409
    assert admin.delete(f"/api/users/{me['id']}").status_code == 409
    assert admin.put(f"/api/users/{me['id']}", json={**base, "role": "admin"}).status_code == 200


def test_admin_can_delete_other(admin, make_user):
    u = make_user("x@test.com")
    assert admin.delete(f"/api/users/{u.id}").status_code == 204


# ---------- agentes ----------


def test_agent_create_update_get(admin):
    r = admin.post("/api/agents", json=AGENT_BODY)
    assert r.status_code == 201 and r.json()["document_count"] == 0
    aid = r.json()["id"]
    r = admin.put(f"/api/agents/{aid}", json={**AGENT_BODY, "name": "Novo", "rag_min_score": 0.5})
    assert r.status_code == 200 and r.json()["name"] == "Novo" and r.json()["stale_chunks"] == 0
    assert admin.get(f"/api/agents/{aid}").json()["rag_min_score"] == 0.5


def test_agent_validation(admin):
    assert admin.post("/api/agents", json={**AGENT_BODY, "stt": []}).status_code == 422
    assert admin.post("/api/agents", json={**AGENT_BODY, "rag_min_score": 2}).status_code == 422
    assert admin.get("/api/agents/999").status_code == 404


def test_agent_delete_in_use_409(admin, make_agent):
    a = make_agent()
    admin.post("/api/numbers", json=number_body(agent_id=a.id))
    assert admin.delete(f"/api/agents/{a.id}").status_code == 409


def test_agent_delete_free(admin, make_agent):
    a = make_agent()
    assert admin.delete(f"/api/agents/{a.id}").status_code == 204


def test_upload_txt_extracts_text_and_queues_ingest(admin, make_agent, monkeypatch, db):
    from core import rag
    calls = []

    async def fake_ingest(doc_id, content):
        calls.append((doc_id, content))

    monkeypatch.setattr(rag, "ingest", fake_ingest)
    a = make_agent()
    r = admin.post(f"/api/agents/{a.id}/documents", files={"file": ("a.txt", "olá mundo".encode())})
    assert r.status_code == 201 and r.json()["status"] == "processing"
    assert calls == [(r.json()["id"], "olá mundo")]
    assert admin.post(f"/api/agents/{a.id}/documents", files={"file": ("a.exe", b"x")}).status_code == 422
    assert len(admin.get(f"/api/agents/{a.id}/documents").json()) == 1
    assert admin.delete(f"/api/documents/{r.json()['id']}").status_code == 204


def test_search_uses_rag_search(admin, make_agent, monkeypatch):
    from core import rag

    async def fake_search(agent, q):
        return [("trecho", 0.9), ("ruim", 0.1)]

    monkeypatch.setattr(rag, "search", fake_search)
    a = make_agent()
    r = admin.post(f"/api/agents/{a.id}/search", json={"query": "x"})
    assert [x["relevant"] for x in r.json()] == [True, False]


# ---------- test-call ----------


def test_test_call_requires_target(admin):
    assert admin.post("/api/test-call", json={}).status_code == 422


def test_test_call_agent_returns_token(admin, make_agent):
    a = make_agent()
    r = admin.post("/api/test-call", json={"agent_id": a.id})
    assert r.status_code == 200
    body = r.json()
    assert body["token"].count(".") == 2 and body["room"].startswith("teste-")
    assert body["server_url"] == "wss://test.livekit.invalid"


def test_test_call_number_and_404(admin, make_agent):
    a = make_agent()
    n = admin.post("/api/numbers", json=number_body(agent_id=a.id)).json()
    assert admin.post("/api/test-call", json={"number_id": n["id"]}).status_code == 200
    assert admin.post("/api/test-call", json={"number_id": 999}).status_code == 404


# ---------- console ----------


@pytest.fixture
def scenario(make_user, make_queue, db):
    q1, q2 = make_queue("Q1"), make_queue("Q2")
    att1 = make_user("att1@test.com", queues=[q1])
    att2 = make_user("att2@test.com", queues=[q2])

    def call(queue, status="waiting_human", room="r"):
        c = coredb.Call(room=room, queue_id=queue.id, status=status)
        db.add(c)
        db.commit()
        return c
    return q1, q2, att1, att2, call


def test_console_lists_only_waiting_from_own_queues(scenario, login):
    q1, q2, *_, call = scenario
    c1, c2 = call(q1, room="a"), call(q2, room="b")
    call(q1, status="ai", room="c")
    ids = [c["id"] for c in login("att1@test.com").get("/api/console").json()["waiting"]]
    assert ids == [c1.id]
    assert c2.id not in ids


def test_console_accept_flow(scenario, login, make_user, db):
    q1, _, att1, _, call = scenario
    make_user("att3@test.com", queues=[q1])
    c = call(q1, room="roomx")
    cl = login("att1@test.com")
    r = cl.post(f"/api/console/calls/{c.id}/accept")
    assert r.status_code == 200 and r.json()["room"] == "roomx" and r.json()["token"].count(".") == 2
    db.refresh(c)
    assert (c.status, c.attendant_id) == ("with_human", att1.id)
    # o mesmo atendente pode pegar um token novo (recarregou a página); outra pessoa não
    assert cl.post(f"/api/console/calls/{c.id}/accept").status_code == 200
    assert login("att3@test.com").post(f"/api/console/calls/{c.id}/accept").status_code == 409
    assert [x["id"] for x in cl.get("/api/console").json()["active"]] == [c.id]


def test_console_accept_other_queue_403(scenario, login):
    q1, *_, call = scenario
    c = call(q1)
    assert login("att2@test.com").post(f"/api/console/calls/{c.id}/accept").status_code == 403


def test_console_accept_404(scenario, login):
    assert login("att1@test.com").post("/api/console/calls/999/accept").status_code == 404


class FakeLK:
    deleted = []
    err = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    @property
    def room(self):
        return self

    async def delete_room(self, req):
        if FakeLK.err:
            raise FakeLK.err
        FakeLK.deleted.append(req.room)


@pytest.fixture
def fake_lk(monkeypatch):
    import apps.api.main as m
    FakeLK.deleted, FakeLK.err = [], None
    monkeypatch.setattr(m.lkapi, "LiveKitAPI", FakeLK)
    return FakeLK


def test_hangup_marks_ended(scenario, login, db, fake_lk):
    q1, *_, call = scenario
    c = call(q1, room="roomh")
    cl = login("att1@test.com")
    cl.post(f"/api/console/calls/{c.id}/accept")
    assert cl.post(f"/api/console/calls/{c.id}/hangup").json() == {"ok": True}
    db.refresh(c)
    assert c.status == "ended" and c.ended_at is not None
    assert fake_lk.deleted == ["roomh"]


def test_hangup_other_attendant_403_admin_ok(scenario, login, admin, db, fake_lk):
    q1, *_, call = scenario
    c = call(q1)
    login("att1@test.com").post(f"/api/console/calls/{c.id}/accept")
    assert login("att2@test.com").post(f"/api/console/calls/{c.id}/hangup").status_code == 403
    assert admin.post(f"/api/console/calls/{c.id}/hangup").status_code == 200


def test_hangup_room_not_found_still_ends(scenario, login, db, fake_lk):
    from livekit import api as lkapi
    q1, *_, call = scenario
    c = call(q1)
    cl = login("att1@test.com")
    cl.post(f"/api/console/calls/{c.id}/accept")
    fake_lk.err = lkapi.TwirpError(code="not_found", msg="x", status=404)
    assert cl.post(f"/api/console/calls/{c.id}/hangup").status_code == 200
    db.refresh(c)
    assert c.status == "ended"


# ---------- chamadas ----------


def test_calls_list_and_get_permissions(scenario, login, admin):
    q1, q2, *_, call = scenario
    c = call(q1)
    assert [x["id"] for x in admin.get("/api/calls").json()] == [c.id]
    assert login("att1@test.com").get(f"/api/calls/{c.id}").status_code == 200
    assert login("att2@test.com").get(f"/api/calls/{c.id}").status_code == 403


# ---------- recados ----------


@pytest.fixture
def msgs(scenario, db):
    q1, q2, *_ = scenario
    m1 = coredb.Message(queue_id=q1.id, name="A", message="m1")
    m2 = coredb.Message(queue_id=q2.id, name="B", message="m2")
    db.add_all([m1, m2])
    db.commit()
    return m1, m2


def test_messages_scoped_by_queue(msgs, login, admin):
    m1, m2 = msgs
    assert [m["id"] for m in login("att1@test.com").get("/api/messages").json()] == [m1.id]
    assert {m["id"] for m in admin.get("/api/messages").json()} == {m1.id, m2.id}


def test_message_patch_done_and_forbidden(msgs, login, db):
    m1, m2 = msgs
    cl = login("att1@test.com")
    assert cl.patch(f"/api/messages/{m1.id}", json={"done": True}).status_code == 200
    db.refresh(m1)
    assert m1.done is True
    assert cl.patch(f"/api/messages/{m2.id}", json={"done": True}).status_code == 403
    db.refresh(m2)
    assert m2.done is False
    assert cl.patch("/api/messages/999", json={"done": True}).status_code == 404
