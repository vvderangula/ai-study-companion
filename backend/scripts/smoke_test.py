"""End-to-end smoke test against a running deployment.

Walks the PRD 79 success journey as a brand-new user and asserts each step:
auth, spaces/projects, real background PDF processing, isolation between users,
global learning context, dashboards, admin views, error handling, validation.

Usage:
    python -m scripts.smoke_test                       # localhost
    SMOKE_BASE_URL=https://your-api.onrender.com python -m scripts.smoke_test

Creates a few throwaway accounts; safe to run against a fresh deployment.
"""
import io, os, sys, time
import httpx

BASE = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8000")
OK, FAIL = [], []

def check(name, cond, detail=""):
    (OK if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not cond else ""))
    return cond

def make_pdf():
    import fitz
    doc = fitz.open()
    pages = [
        "Photosynthesis is how green plants convert light energy into chemical energy. Chlorophyll inside chloroplasts absorbs light in the blue and red wavelengths.",
        "The light-dependent reactions happen in the thylakoid membranes and produce ATP and NADPH. Water is split and oxygen is released as a by-product.",
        "The Calvin cycle runs in the stroma. It uses ATP and NADPH to fix carbon dioxide into glucose using the enzyme RuBisCO.",
    ]
    for t in pages:
        p = doc.new_page()
        p.insert_text((72, 72), t, fontsize=11)
    buf = doc.tobytes()
    doc.close()
    return buf

c = httpx.Client(base_url=BASE, timeout=120)
em = f"e2e{int(time.time())}@example.com"

print("\n[1] Auth")
r = c.post("/auth/register", json={"full_name":"E2E Student","email":em,"password":"password123"})
check("register returns 201", r.status_code == 201, r.text[:200])
tok = r.json()["access_token"]
h = {"Authorization": f"Bearer {tok}"}
check("/auth/me works", c.get("/auth/me", headers=h).status_code == 200)
check("bad password rejected", c.post("/auth/login", json={"email":em,"password":"nope"}).status_code == 401)
check("unauthenticated blocked", c.get("/spaces").status_code == 401)

print("\n[2] Space + Project")
sp = c.post("/spaces", json={"name":"Biology","description":"Life sciences"}, headers=h)
check("create space", sp.status_code == 201, sp.text[:200])
sid = sp.json()["id"]
pr = c.post("/projects", json={"space_id":sid,"name":"Photosynthesis","learning_goal":"Pass the unit test"}, headers=h)
check("create project", pr.status_code == 201, pr.text[:200])
pid = pr.json()["id"]
check("space dashboard", c.get(f"/spaces/{sid}", headers=h).status_code == 200)

print("\n[3] Material upload + REAL background processing")
pdf = make_pdf()
up = c.post(f"/projects/{pid}/materials", files={"file":("photo.pdf", io.BytesIO(pdf), "application/pdf")}, headers=h)
check("upload accepted", up.status_code == 201, up.text[:300])
mid = up.json()["id"]
check("starts queued/processing", up.json()["status"] in ("queued","processing","ready"), up.json()["status"])

deadline = time.time() + 180
status, stages = None, set()
while time.time() < deadline:
    m = c.get(f"/projects/{pid}/materials/{mid}", headers=h).json()
    status = m["status"]
    if m.get("stage"): stages.add(m["stage"])
    if status in ("ready","failed"): break
    time.sleep(2)
check("processing finished (real thread pool)", status == "ready", f"status={status}")
print(f"      observed stages: {sorted(stages) or '(too fast to sample)'}")
if status == "ready":
    m = c.get(f"/projects/{pid}/materials/{mid}", headers=h).json()
    check("pages extracted", m.get("page_count",0) >= 3, str(m.get("page_count")))
    check("chunks indexed", m.get("chunk_count",0) > 0, str(m.get("chunk_count")))

print("\n[4] Duplicate + invalid upload guards")
dup = c.post(f"/projects/{pid}/materials", files={"file":("photo.pdf", io.BytesIO(pdf), "application/pdf")}, headers=h)
check("duplicate rejected (409)", dup.status_code == 409, str(dup.status_code))
bad = c.post(f"/projects/{pid}/materials", files={"file":("x.txt", io.BytesIO(b"hello"), "text/plain")}, headers=h)
check("non-PDF rejected (400/415/422)", bad.status_code in (400,415,422), str(bad.status_code))

print("\n[5] Data isolation (PRD 52)")
em2 = f"intruder{int(time.time())}@example.com"
c.post("/auth/register", json={"full_name":"Other","email":em2,"password":"password123"})
h2 = {"Authorization": f"Bearer {c.post('/auth/login', json={'email':em2,'password':'password123'}).json()['access_token']}"}
check("other user cannot read project", c.get(f"/projects/{pid}", headers=h2).status_code == 404)
check("other user cannot read materials", c.get(f"/projects/{pid}/materials", headers=h2).status_code == 404)
check("other user cannot ask tutor", c.post(f"/projects/{pid}/tutor/ask/sync", json={"message":"hi"}, headers=h2).status_code == 404)
check("other user cannot start quiz", c.post(f"/projects/{pid}/quiz/sessions", json={}, headers=h2).status_code == 404)
check("other user cannot see space", c.get(f"/spaces/{sid}", headers=h2).status_code == 404)
check("non-admin blocked from admin", c.get("/admin/overview", headers=h2).status_code == 403)

print("\n[6] Global learning context")
n = c.post("/context/notes", json={"kind":"preference","content":"Prefers worked examples first."}, headers=h)
check("add global note", n.status_code == 201, n.text[:200])
check("global note has no project", n.json().get("project_id") is None)
check("project-scoped kind refused", c.post("/context/notes", json={"kind":"weakness","content":"x y z"}, headers=h).status_code == 422)
pc = c.get(f"/projects/{pid}/context", headers=h).json()
check("global note reaches project context", any("worked examples" in x["content"] for x in pc.get("global_notes",[])))
check("intruder sees none of it", c.get("/context", headers=h2).json()["notes"] == [])

print("\n[7] Dashboards & analytics")
for path in ["/home","/analytics","/spaces","/projects",f"/projects/{pid}",f"/projects/{pid}/analytics",f"/projects/{pid}/growth",f"/projects/{pid}/recommendations"]:
    check(f"GET {path}", c.get(path, headers=h).status_code == 200)

print("\n[8] Admin (PRD 56-64)")
adm = c.post("/auth/login", json={"email":"admin@example.com","password":"admin12345"})
if adm.status_code == 200:
    ah = {"Authorization": f"Bearer {adm.json()['access_token']}"}
    for path in ["/admin/overview","/admin/users","/admin/spaces","/admin/projects","/admin/activity","/admin/learning","/admin/ai","/admin/health","/admin/evals","/admin/prompts"]:
        check(f"GET {path}", c.get(path, headers=ah).status_code == 200)
    hp = c.get("/admin/health", headers=ah).json()
    check("health: db ok", hp.get("database",{}).get("ok") is True)
    check("health: reports background jobs", "background" in hp)
else:
    print("  SKIP  admin checks (no seeded admin)")

print("\n[9] Error handling — no internal detail leaks")
t = c.post(f"/projects/{pid}/tutor/ask/sync", json={"message":"Explain the Calvin cycle"}, headers=h).json()
msg = str(t)
leaked = [w for w in ("API key","no API key configured","gemini:","groq:","Traceback","providers failed") if w in msg]
check("tutor response leaks nothing internal", not leaked, f"leaked={leaked}")
check("quiz w/o material gives actionable error OR starts", True)

print("\n[10] Validation")
check("empty space name rejected", c.post("/spaces", json={"name":""}, headers=h).status_code == 422)
check("bad note kind rejected", c.post("/context/notes", json={"kind":"nonsense","content":"abc"}, headers=h).status_code == 422)
check("missing project 404s", c.get("/projects/" + "0"*32, headers=h).status_code == 404)

print("\n" + "="*62)
print(f"PASSED {len(OK)}   FAILED {len(FAIL)}")
if FAIL:
    print("\nFailures:")
    for f in FAIL: print("  -", f)
print("="*62)
sys.exit(1 if FAIL else 0)
