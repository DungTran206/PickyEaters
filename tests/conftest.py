import json
import os
import tempfile

import pytest

# Isolate the SQLite database BEFORE any test module imports database.db (DB_PATH is read at
# import time). Tests call reset_database(); without this they would wipe the app's
# data/food_agent.db. load_dotenv() does not override an already-set variable.
_TEST_DIR = tempfile.mkdtemp(prefix="pickyeaters-test-")
os.environ["DATABASE_PATH"] = os.path.join(_TEST_DIR, "food_agent.db")

# The app has no default delivery location, so test users get an explicit one here.
# user_01 lives in Cầu Giấy (typed address); user_new has no location on purpose.
import database.db as _db  # noqa: E402  (must follow the DATABASE_PATH override)

with open(_db.USERS_SEED_PATH, encoding="utf-8") as _f:
    _users = json.load(_f)
for _u in _users:
    if _u["user_id"] == "user_01":
        _u.update(address="Cầu Giấy, Hà Nội", district="Cầu Giấy, Hà Nội")
_db.USERS_SEED_PATH = os.path.join(_TEST_DIR, "users.json")
with open(_db.USERS_SEED_PATH, "w", encoding="utf-8") as _f:
    json.dump(_users, _f, ensure_ascii=False)


@pytest.fixture(autouse=True)
def disable_external_apis_in_tests(monkeypatch):
    """Ensure automated tests run hermetically without hitting live external APIs.

    Real API credentials remain intact in .env for REPL and live application usage.
    """
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
