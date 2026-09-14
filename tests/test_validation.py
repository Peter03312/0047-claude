"""整单拒绝：环、悬空引用、同场景增删同一事实、重复 id、未知入口。"""

import pytest

from app.errors import GraphValidationError
from app.service import analyze_graph


def _issue_codes(exc: GraphValidationError) -> list[str]:
    return [issue["code"] for issue in exc.issues]


def test_cycle_is_rejected_with_cycle_path(make_scene, make_graph):
    scenes = [
        make_scene("a", targets=["b"]),
        make_scene("b", targets=["c"]),
        make_scene("c", targets=["a"]),
    ]
    with pytest.raises(GraphValidationError) as exc_info:
        analyze_graph(make_graph("a", scenes))
    codes = _issue_codes(exc_info.value)
    assert codes == ["cycle_detected"]
    cycle = exc_info.value.issues[0]["cycle"]
    assert cycle[0] == cycle[-1]
    assert set(cycle) == {"a", "b", "c"}


def test_self_loop_is_rejected(make_scene, make_graph):
    with pytest.raises(GraphValidationError) as exc_info:
        analyze_graph(make_graph("a", [make_scene("a", targets=["a"])]))
    assert _issue_codes(exc_info.value) == ["cycle_detected"]


def test_dangling_edge_is_rejected(make_scene, make_graph):
    scenes = [
        make_scene("a", targets=["nowhere"]),
    ]
    with pytest.raises(GraphValidationError) as exc_info:
        analyze_graph(make_graph("a", scenes))
    issue = exc_info.value.issues[0]
    assert issue["code"] == "dangling_edge"
    assert issue["scene"] == "a"
    assert issue["edge"] == 0
    assert issue["target"] == "nowhere"


def test_add_remove_same_fact_is_rejected(make_scene, make_graph):
    scenes = [make_scene("a", adds=["secret"], removes=["secret"])]
    with pytest.raises(GraphValidationError) as exc_info:
        analyze_graph(make_graph("a", scenes))
    issue = exc_info.value.issues[0]
    assert issue["code"] == "add_remove_same_fact"
    assert issue["scene"] == "a"
    assert issue["fact"] == "secret"


def test_duplicate_scene_id_is_rejected(make_scene, make_graph):
    scenes = [
        make_scene("a", targets=["b"]),
        make_scene("b"),
        make_scene("b", adds=["x"]),
    ]
    with pytest.raises(GraphValidationError) as exc_info:
        analyze_graph(make_graph("a", scenes))
    assert _issue_codes(exc_info.value) == ["duplicate_scene"]


def test_unknown_entry_is_rejected(make_scene, make_graph):
    with pytest.raises(GraphValidationError) as exc_info:
        analyze_graph(make_graph("missing", [make_scene("a")]))
    assert _issue_codes(exc_info.value) == ["unknown_entry"]


def test_multiple_issues_are_all_reported(make_scene, make_graph):
    # 同场景增删冲突 + 悬空边同时存在：一次返回全部问题。
    scenes = [
        make_scene(
            "a", adds=["x"], removes=["x"], targets=["ghost"]
        ),
    ]
    with pytest.raises(GraphValidationError) as exc_info:
        analyze_graph(make_graph("a", scenes))
    codes = _issue_codes(exc_info.value)
    assert "add_remove_same_fact" in codes
    assert "dangling_edge" in codes


def test_entry_requires_has_length_zero_counterexample(make_scene, make_graph):
    # 入口的 requires 在初始 adds 注入之前检查，必然缺失。
    report = analyze_graph(
        make_graph("start", [make_scene("start", adds=["secret"], requires=["secret"])])
    )
    assert report["violated"] is True
    ce = report["violations"][0]["counterexample"]
    assert ce["length"] == 0
    assert ce["edge_indices"] == []
    assert ce["route"] == [{"scene": "start", "choice": None}]
