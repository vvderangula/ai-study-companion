from tests.conftest import register


def test_register_login_me(client):
    r = client.post("/auth/register", json={"full_name": "A", "email": "a@example.com", "password": "password123"})
    assert r.status_code == 201
    assert r.json()["role"] == "learner"
    dup = client.post("/auth/register", json={"full_name": "A", "email": "a@example.com", "password": "password123"})
    assert dup.status_code == 409
    bad = client.post("/auth/login", json={"email": "a@example.com", "password": "wrong-password"})
    assert bad.status_code == 401
    ok = client.post("/auth/login", json={"email": "a@example.com", "password": "password123"})
    assert ok.status_code == 200
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {ok.json()['access_token']}"})
    assert me.json()["email"] == "a@example.com"


def test_admin_role_from_env(client):
    r = client.post("/auth/register", json={"full_name": "Admin", "email": "admin@example.com", "password": "password123"})
    assert r.json()["role"] == "admin"


def test_requires_auth(client):
    assert client.get("/spaces").status_code == 401
    assert client.get("/home", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_validation_errors(client, auth):
    r = client.post("/spaces", json={"name": ""}, headers=auth)
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"


def test_project_isolation_between_users(client, auth, project):
    other = register(client, "other@example.com")
    pid = project["project"]["id"]
    assert client.get(f"/projects/{pid}", headers=other).status_code == 404
    assert client.get(f"/projects/{pid}/materials", headers=other).status_code == 404
    assert client.post(f"/projects/{pid}/tutor/ask/sync", json={"message": "hi"}, headers=other).status_code == 404
    assert client.post(f"/projects/{pid}/quiz/sessions", json={}, headers=other).status_code == 404
    assert client.get(f"/spaces/{project['space']['id']}", headers=other).status_code == 404
    # own access still fine
    assert client.get(f"/projects/{pid}", headers=auth).status_code == 200
    # cannot create a project in someone else's space
    r = client.post("/projects", json={"space_id": project["space"]["id"], "name": "Hijack"}, headers=other)
    assert r.status_code == 404


def test_admin_routes_require_admin(client, auth):
    assert client.get("/admin/overview", headers=auth).status_code == 403
    admin = register(client, "admin@example.com")
    assert client.get("/admin/overview", headers=admin).status_code == 200


def test_global_context_notes(client, auth, project):
    """Global notes are user-level, reach every project, and reject project-scoped kinds."""
    assert client.get("/context", headers=auth).json()["notes"] == []

    created = client.post("/context/notes", json={"kind": "preference", "content": "Prefers worked examples."}, headers=auth)
    assert created.status_code == 201
    assert created.json()["project_id"] is None

    ctx = client.get("/context", headers=auth).json()
    assert [n["content"] for n in ctx["notes"]] == ["Prefers worked examples."]
    assert "worked examples" in ctx["prompt_block"]

    # Concept-bound kinds stay project-scoped (PRD 3.1) and are refused here.
    assert client.post("/context/notes", json={"kind": "weakness", "content": "Bad at recursion."}, headers=auth).status_code == 422

    # The note reaches the project's tutor context, labelled as cross-project.
    pctx = client.get(f"/projects/{project['project']['id']}/context", headers=auth).json()
    assert [n["content"] for n in pctx["global_notes"]] == ["Prefers worked examples."]
    assert "applies across all their projects" in pctx["prompt_block"]

    note_id = ctx["notes"][0]["id"]
    assert client.delete(f"/context/notes/{note_id}", headers=auth).status_code == 204
    assert client.get("/context", headers=auth).json()["notes"] == []
    # Deleting again is a 404, not a silent success.
    assert client.delete(f"/context/notes/{note_id}", headers=auth).status_code == 404


def test_global_notes_are_private_to_their_owner(client, auth):
    client.post("/context/notes", json={"kind": "goal", "content": "Certification in March."}, headers=auth)
    other = register(client, "stranger@example.com")
    assert client.get("/context", headers=other).json()["notes"] == []
