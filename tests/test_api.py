"""HTTP 交付层测试。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _diamond_payload():
    return {
        "entry": "start",
        "scenes": [
            {
                "id": "start",
                "adds": ["secret"],
                "choices": [
                    {"target": "branch_a", "label": "走天台"},
                    {"target": "branch_b", "label": "走走廊"},
                ],
            },
            {"id": "branch_a", "choices": [{"target": "meet"}]},
            {
                "id": "branch_b",
                "removes": ["secret"],
                "choices": [{"target": "meet"}],
            },
            {"id": "meet", "requires": ["secret"]},
        ],
    }


def test_healthz():
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_analyze_reports_violation_with_route():
    res = client.post("/api/analyze", json=_diamond_payload())
    assert res.status_code == 200
    body = res.json()
    assert body["violated"] is True
    violation = body["violations"][0]
    assert violation["scene"] == "meet"
    assert violation["fact"] == "secret"
    route = [hop["scene"] for hop in violation["counterexample"]["route"]]
    assert route == ["start", "branch_b", "meet"]
    assert violation["counterexample"]["edge_indices"] == [1, 0]


def test_structure_rejection_returns_422_with_issues():
    payload = _diamond_payload()
    payload["scenes"][0]["choices"][1]["target"] = "ghost"
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 422
    body = res.json()
    assert body["ok"] is False
    assert body["error"] == "graph_validation_failed"
    assert body["issues"][0]["code"] == "dangling_edge"


def test_bad_shape_returns_422():
    res = client.post("/api/analyze", json={"entry": "start", "scenes": []})
    assert res.status_code == 422
    assert res.json()["error"] == "invalid_request"


def test_unknown_field_is_forbidden():
    payload = _diamond_payload()
    payload["scenes"][0]["narrative"] = "放学后……"
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 422


def test_output_is_stable_for_same_input():
    payload = _diamond_payload()
    first = client.post("/api/analyze", json=payload).json()
    second = client.post("/api/analyze", json=payload).json()
    assert first == second
