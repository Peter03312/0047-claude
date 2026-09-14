"""菱形汇合：多支线知识必须按“所有路径交集”判定，不能用并集放行。"""

from conftest import scene_report, violations_for


def _diamond(make_scene, *, b_learns_secret=False):
    """菱形：start --A--> meet，start --B--> meet。

    A 支始终持有秘密；B 支在自己的场景移除秘密（走 B 的读者没看到秘密）。
    汇合场景 meet 要求读者知道秘密。
    """
    return [
        make_scene(
            "start",
            adds=["secret"],
            targets=["branch_a", "branch_b"],
        ),
        make_scene("branch_a", targets=["meet"]),
        make_scene(
            "branch_b",
            removes=[] if b_learns_secret else ["secret"],
            adds=["secret"] if b_learns_secret else [],
            targets=["meet"],
        ),
        make_scene("meet", requires=["secret"]),
    ]


def test_diamond_merge_blocks_union_release(make_scene, make_graph, analyze):
    graph = make_graph("start", _diamond(make_scene))
    report = analyze(graph)

    assert report["violated"] is True
    violations = violations_for(report, "meet")
    assert len(violations) == 1
    assert violations[0]["fact"] == "secret"

    ce = violations[0]["counterexample"]
    # 最短穿帮路线：start -> branch_b -> meet（边序 1 再 0）
    assert ce["length"] == 2
    assert ce["edge_indices"] == [1, 0]
    assert [hop["scene"] for hop in ce["route"]] == [
        "start",
        "branch_b",
        "meet",
    ]
    assert ce["arriving_facts"] == []  # 走 B 的读者确实不知道秘密


def test_diamond_merge_satisfied_when_every_path_holds_fact(
    make_scene, make_graph, analyze
):
    graph = make_graph("start", _diamond(make_scene, b_learns_secret=True))
    report = analyze(graph)

    assert report["violated"] is False
    meet = scene_report(report, "meet")
    assert meet["guaranteed_facts_on_entry"] == ["secret"]
    assert meet["requires"][0]["satisfied"] is True
    assert meet["requires"][0]["counterexample"] is None
    assert report["violations"] == []


def test_diamond_guaranteed_sets_are_intersection(make_scene, make_graph, analyze):
    # A 支独有 note_a，B 支独有 note_b，公共事实 secret 只在 A 支保留。
    scenes = [
        make_scene(
            "start", adds=["secret"], targets=["branch_a", "branch_b"]
        ),
        make_scene("branch_a", adds=["note_a"], targets=["meet"]),
        make_scene(
            "branch_b", removes=["secret"], adds=["note_b"], targets=["meet"]
        ),
        make_scene("meet"),
    ]
    report = analyze(make_graph("start", scenes))
    meet = scene_report(report, "meet")
    # 交集：note_a / note_b 都只在一条支线上，不能带进公共场景。
    assert meet["guaranteed_facts_on_entry"] == []
