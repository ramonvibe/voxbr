import os

# Antes de importar core.db / app. load_dotenv() não sobrescreve variáveis já definidas.
os.environ["DATABASE_URL"] = "postgresql+psycopg://voxbr:voxbr@127.0.0.1:5435/voxbr_test"
os.environ["SESSION_SECRET"] = "test-secret-test-secret-test-secret"
os.environ["LIVEKIT_URL"] = "wss://test.livekit.invalid"
os.environ["LIVEKIT_API_KEY"] = "testkey"
os.environ["LIVEKIT_API_SECRET"] = "testsecret-testsecret-testsecret-123"
os.environ["ADMIN_EMAIL"] = "boot@test.com"
os.environ["ADMIN_PASSWORD"] = "bootpass123"

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from core import db as coredb  # noqa: E402
from core.auth import hash_password  # noqa: E402

assert coredb.DATABASE_URL.endswith("/voxbr_test"), "testes só rodam no banco voxbr_test"

PASSWORD = "senha-forte-1"


@pytest.fixture(scope="session", autouse=True)
def _schema():
    coredb.init_db()


@pytest.fixture(autouse=True)
def _clean():
    tables = ", ".join(t.name for t in coredb.Base.metadata.sorted_tables)
    with coredb.engine.begin() as c:
        c.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def db():
    with coredb.SessionLocal() as s:
        yield s


@pytest.fixture
def make_user(db):
    def _make(email="u@test.com", role="attendant", active=True, queues=(), name=None):
        u = coredb.User(email=email, name=name or email.split("@")[0], password_hash=hash_password(PASSWORD),
                        role=role, active=active)
        u.queues = list(queues)
        db.add(u)
        db.commit()
        return u
    return _make


@pytest.fixture
def make_queue(db):
    def _make(name="Fila", **kw):
        q = coredb.Queue(name=name, **kw)
        db.add(q)
        db.commit()
        return q
    return _make


@pytest.fixture
def make_agent(db):
    def _make(name="Agente"):
        a = coredb.AgentProfile(name=name, stt=[], llm=[], tts=[], embedding={})
        db.add(a)
        db.commit()
        return a
    return _make


@pytest.fixture
def app_client():
    from apps.api.main import app
    return app


@pytest.fixture
def client(app_client):
    return TestClient(app_client)


@pytest.fixture
def login(app_client):
    def _login(email):
        c = TestClient(app_client)
        r = c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        return c
    return _login


@pytest.fixture
def admin(make_user, login):
    make_user("admin@test.com", role="admin", name="Admin")
    return login("admin@test.com")
