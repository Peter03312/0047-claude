"""移除后再使用：秘密被某场景 removes 后，后续场景不能继续要求它。"""

from conftest import scene_report, violations_for


def test_removed_fact_cannot_be_required_later(make_scene, make_graph, analyze):
    scenes = [
        make_scene(
            "start", adds=["secret", "hall_pass"], targets=["corridor"]
        ),
        make_scene(
            "corridor", removes=["secret"], targets=["storage"]
        ),
        make_scene("storage", requires=["secret"]),
    ]
    report = analyze(make_graph("start", scenes))

    assert report["violated"] is True
    ce = violations_for(report, "storage")[0]["counterexample"]
    assert ce["length"] == 2
    assert ce["edge_indices"] == [0, 0]
    # 另一条事实不受移除影响，应出现在到达事实集中。
    assert ce["arriving_facts"] == ["hall_pass"]


def test_readded_fact_satisfies_later_requirement(make_scene, make_graph, analyze):
    scenes = [
        make_scene("start", adds=["secret"], targets=["corridor"]),
        make_scene("corridor", removes=["secret"], targets=["rooftop"]),
        make_scene("rooftop", adds=["secret"], targets=["storage"]),
        make_scene("storage", requires=["secret"]),
    ]
    report = analyze(make_graph("start", scenes))

    assert report["violated"] is False
    storage = scene_report(report, "storage")
    assert storage["guaranteed_facts_on_entry"] == ["secret"]


def test_remove_then_use_at_branch_reports_branch_route(
    make_scene, make_graph, analyze
):
    # A 支保留秘密，B 支移除；要求秘密的场景在 B 支的下游。
    scenes = [
        make_scene(
            "start", adds=["secret"], targets=["keep_path", "lose_path"]
        ),
        make_scene("keep_path", targets=["join"]),
        make_scene("lose_path", removes=["secret"], targets=["join"]),
        make_scene("join", targets=["after"]),
        make_scene("after", requires=["secret"]),
    ]
    report = analyze(make_graph("start", scenes))
    ce = violations_for(report, "after")[0]["counterexample"]
    assert [hop["scene"] for hop in ce["route"]] == [
        "start",
        "lose_path",
        "join",
        "after",
    ]
    assert ce["edge_indices"] == [1, 0, 0]
