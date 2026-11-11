def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "sandbox": "local"}


def test_problem_endpoints(client):
    ids = [p["id"] for p in client.get("/problems").json()]
    assert {"P001", "P002", "P003"} <= set(ids)
    p = client.get("/problems/P001").json()
    assert p["test_count"] >= 3 and "Tổng" in p["title"]
    assert client.get("/problems/NOPE").status_code == 404


def test_submit_store_and_history(client):
    src = '#include <stdio.h>\nint main(void){int n; scanf("%d", n); return 0;}'
    r = client.post("/submit", json={"student_id": "sv9", "problem_id": "P001", "source_code": src})
    assert r.status_code == 200
    rep = r.json()
    assert "SCANF_MISSING_AMP" in {f["bug_pattern"] for f in rep["findings"]}

    again = client.get(f"/submissions/{rep['submission_id']}").json()
    assert again["grading"]["verdict"] == rep["grading"]["verdict"]

    hist = client.get("/students/sv9/submissions").json()
    assert [h["id"] for h in hist] == [rep["submission_id"]]


def test_submit_validation(client):
    bad = {"student_id": "sv1", "problem_id": "P001", "source_code": ""}
    assert client.post("/submit", json=bad).status_code == 422
    unknown = {"student_id": "sv1", "problem_id": "P999", "source_code": "int main(){}"}
    assert client.post("/submit", json=unknown).status_code == 404


def test_ui_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Nộp bài" in r.text
