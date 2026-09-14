"""不可达场景：分析只覆盖入口可达场景，孤立场景仅列出、不参与判定。"""

from conftest import scene_report, violations_for


def test_unreachable_scene_is_listed_and_not_analyzed(
    make_scene, make_graph, analyze
):
    scenes = [
        make_scene("start", adds=["secret"], targets=["meet"]),
        make_scene("meet", requires=["secret"]),
        # 没有任何边指向 orphan；即使它要求缺失事实，也不算穿帮。
        make_scene("orphan", requires=["secret"]),
    ]
    report = analyze(make_graph("start", scenes))

    assert report["violated"] is False
    assert report["unreachable_scenes"] == ["orphan"]
    orphan = scene_report(report, "orphan")
    assert orphan == {"id": "orphan", "reachable": False}
    assert report["summary"]["reachable_scenes"] == 2
    assert report["summary"]["unreachable_scenes"] == 1


def test_unreachable_cycle_branch_still_counts(make_scene, make_graph, analyze):
    scenes = [
        make_scene("start", targets=["a"]),
        make_scene("a"),
        make_scene("ghost", targets=["ghost2"]),
        make_scene("ghost2"),
    ]
    report = analyze(make_graph("start", scenes))
    assert report["unreachable_scenes"] == ["ghost", "ghost2"]
    assert violations_for(report, "ghost") == []
