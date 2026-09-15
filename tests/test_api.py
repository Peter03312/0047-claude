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


def _conditional_payload():
    # 走廊支线会丢秘密，但它进入汇合点的选择要求持有秘密才出现：
    # 不知道秘密的读者走不到 meet，不得误报穿帮。
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
                "choices": [
                    {
                        "target": "meet",
                        "available_when": ["secret"],
                    }
                ],
            },
            {"id": "meet", "requires": ["secret"]},
        ],
    }


def test_conditional_choice_excludes_pseudo_counterexample_over_http():
    res = client.post("/api/analyze", json=_conditional_payload())
    assert res.status_code == 200
    body = res.json()
    assert body["violated"] is False
    assert body["violations"] == []
    assert body["unreachable_scenes"] == []
    meet = next(s for s in body["scenes"] if s["id"] == "meet")
    assert meet["guaranteed_facts_on_entry"] == ["secret"]
    assert meet["requires"][0]["satisfied"] is True


def test_fully_closed_target_is_unreachable_over_http():
    payload = _conditional_payload()
    # 天台支也加上永不满足的条件：meet 的所有入边全封闭。
    payload["scenes"][1]["choices"][0]["available_when"] = ["never"]
    payload["scenes"][2]["choices"][0]["available_when"] = ["never"]
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["violated"] is False
    assert body["violations"] == []
    assert body["unreachable_scenes"] == ["meet"]
    meet = next(s for s in body["scenes"] if s["id"] == "meet")
    assert meet == {"id": "meet", "reachable": False}


def test_available_when_wrong_shape_returns_locatable_invalid_request():
    # available_when 必须是字符串列表；这里传成字符串 -> invalid_request，
    # 且 loc 能定位到具体场景、选择与字段。
    payload = _conditional_payload()
    payload["scenes"][2]["choices"][0]["available_when"] = "secret"
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 422
    body = res.json()
    assert body["ok"] is False
    assert body["error"] == "invalid_request"
    locs = [tuple(issue["loc"]) for issue in body["issues"]]
    assert any(
        "scenes" in loc and "choices" in loc and "available_when" in loc
        for loc in locs
    ), locs


def test_available_when_item_wrong_type_returns_invalid_request():
    payload = _conditional_payload()
    payload["scenes"][2]["choices"][0]["available_when"] = [123]
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 422
    body = res.json()
    assert body["error"] == "invalid_request"


def test_unknown_field_inside_choice_is_forbidden():
    payload = _conditional_payload()
    payload["scenes"][2]["choices"][0]["unlock_hint"] = "要知道秘密"
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 422
    assert res.json()["error"] == "invalid_request"


def test_legacy_payload_without_available_when_is_unchanged():
    # 旧请求（完全没有 available_when 字段）行为与响应字段保持不变。
    res = client.post("/api/analyze", json=_diamond_payload())
    assert res.status_code == 200
    body = res.json()
    assert body["violated"] is True
    ce = body["violations"][0]["counterexample"]
    assert ce["edge_indices"] == [1, 0]
    assert [hop["scene"] for hop in ce["route"]] == [
        "start",
        "branch_b",
        "meet",
    ]
    # 响应顶层结构字段保持旧契约。
    assert set(body) == {
        "entry",
        "violated",
        "summary",
        "unreachable_scenes",
        "scenes",
        "violations",
    }
