"""Test fixtures: in-memory Mongo, fake AI provider, hash embeddings, inline jobs."""

import json
import os
import tempfile

os.environ.update({
    "AI_PROVIDER_ORDER": "fake",
    "EMBEDDING_BACKEND": "hash",
    "JOB_BACKEND": "inline",
    "ADMIN_EMAILS": "admin@example.com",
    "UPLOAD_DIR": os.path.join(tempfile.gettempdir(), "studymate-test-uploads"),
    "EVIDENCE_MIN_SIMILARITY": "0.15",
    "MONGO_DB": "studymate_test",
})

import mongomock  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core import db as dbm  # noqa: E402
from app.main import app  # noqa: E402
from app.services.ai import provider as provider_mod  # noqa: E402
from app.services.ai.provider import FakeProvider  # noqa: E402

PDF_TEXT = {
    1: "Photosynthesis is the process by which green plants convert light energy into chemical energy. Chlorophyll in the chloroplasts absorbs light, mostly in the blue and red wavelengths.",
    2: "The light-dependent reactions occur in the thylakoid membranes and produce ATP and NADPH. Water is split, releasing oxygen as a by-product.",
    3: "The Calvin cycle takes place in the stroma. It uses ATP and NADPH to fix carbon dioxide into glucose through the enzyme RuBisCO.",
}


def make_pdf(path: str) -> None:
    import fitz

    doc = fitz.open()
    for _, text in sorted(PDF_TEXT.items()):
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=11)
    doc.save(path)
    doc.close()


def default_handlers() -> dict:
    def tutor(kw):
        system = kw["system"]
        if "(no passages in the project" in system:
            return "I can't find this in your materials. Your materials cover photosynthesis, the light reactions and the Calvin cycle. Try asking about those.\nGROUNDED: no"
        return "Photosynthesis converts light energy into chemical energy using chlorophyll [S1]. The Calvin cycle then fixes carbon dioxide [S2].\nGROUNDED: yes"

    def router(kw):
        last = kw["messages"][-1]["content"].lower()
        if "how am i doing" in last:
            return provider_mod.AIResult(text="", tool_uses=[provider_mod.ToolUse(id="t1", name="get_learning_state", input={})])
        return "NONE"

    def quiz_gen(kw):
        if "Question type: open" in kw["system"]:
            return {"question": "Explain what the Calvin cycle produces and where it happens.", "options": [], "correct_option": None, "reference_answer": "It happens in the stroma and produces glucose using ATP and NADPH.", "rubric": ["stroma", "glucose", "ATP and NADPH"], "explanation": "See page 3.", "source_pages": [3]}
        return {"question": "Where do the light-dependent reactions occur?", "options": ["Thylakoid membranes", "Stroma", "Mitochondria", "Nucleus"], "correct_option": 0, "reference_answer": None, "rubric": [], "explanation": "They occur in the thylakoid membranes (page 2).", "source_pages": [2]}

    def grade(kw):
        answer = kw["system"].split("<answer>")[1].split("</answer>")[0].lower()
        good = "stroma" in answer and "glucose" in answer
        return {"score": 0.9 if good else 0.3, "is_correct": good, "covered_points": ["stroma"] if good else [], "missing_points": [] if good else ["glucose"], "accuracy_issues": [], "feedback": "Good answer." if good else "You missed that the cycle produces glucose. Focus on the outputs of the Calvin cycle."}

    return {
        "tutor": tutor,
        "tutor_router": router,
        "concept_extraction": lambda kw: {"concepts": [
            {"name": "Photosynthesis overview", "description": "Conversion of light energy to chemical energy.", "importance": 0.9, "pages": [1]},
            {"name": "Light-dependent reactions", "description": "Thylakoid reactions producing ATP and NADPH.", "importance": 0.8, "pages": [2]},
            {"name": "Calvin cycle", "description": "Carbon fixation in the stroma producing glucose.", "importance": 0.85, "pages": [3]},
        ]},
        "material_summary": lambda kw: "A three-page primer on photosynthesis.",
        "quiz_generate": quiz_gen,
        "quiz_grade_open": grade,
        "recommend": lambda kw: {"action": "quiz", "title": "Quiz the Calvin cycle", "reason": "Calvin cycle mastery is low.", "concept_names": ["Calvin cycle"], "suggested_prompt": ""},
        "context_update": lambda kw: {"notes": [{"kind": "preference", "content": "Prefers short answers with examples.", "concept_name": None}]},
        "eval_judge": lambda kw: {"accuracy": 0.9, "groundedness": 0.9, "citation_quality": 0.8, "refusal_correct": 1.0, "rationale": "ok"},
    }


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    client = mongomock.MongoClient(tz_aware=True)
    dbm.set_db(client["studymate_test"])
    dbm.init_db()
    fake = FakeProvider()
    fake.handlers = default_handlers()
    provider_mod.set_providers([fake])
    yield fake
    provider_mod.set_providers(None)
    dbm.set_db(None)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def register(client: TestClient, email: str, name: str = "Test User") -> dict:
    r = client.post("/auth/register", json={"full_name": name, "email": email, "password": "password123"})
    assert r.status_code == 201, r.text
    data = r.json()
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest.fixture
def auth(client):
    return register(client, "learner@example.com")


@pytest.fixture
def project(client, auth):
    space = client.post("/spaces", json={"name": "Biology"}, headers=auth).json()
    proj = client.post("/projects", json={"space_id": space["id"], "name": "Photosynthesis", "learning_goal": "Pass the unit test"}, headers=auth).json()
    return {"space": space, "project": proj}


@pytest.fixture
def ready_project(client, auth, project, tmp_path):
    pdf = tmp_path / "photo.pdf"
    make_pdf(str(pdf))
    with pdf.open("rb") as fh:
        r = client.post(f"/projects/{project['project']['id']}/materials", files={"file": ("photo.pdf", fh, "application/pdf")}, headers=auth)
    assert r.status_code == 201, r.text
    material = r.json()
    assert material["status"] == "ready", json.dumps(material, indent=1)
    return {**project, "material": material}
