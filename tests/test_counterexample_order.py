"""反例裁决：先路径长度，再按边序（下标序列字典序）。"""

from conftest import violations_for


def test_tie_breaks_by_edge_order(make_scene, make_graph, analyze):
    # 两条等长坏路：边序 [1,0] 与 [0,0]，必须取 [0,0]。
    scenes = [
        make_scene(
            "start", adds=["secret"], targets=["lose_first", "keep_first"]
        ),
        # 边 0：一上来就丢秘密
        make_scene("lose_first", removes=["secret"], targets=["meet"]),
        # 边 1：先保留，下一跳再丢
        make_scene("keep_first", targets=["lose_later"]),
        make_scene("lose_later", removes=["secret"], targets=["meet"]),
        make_scene("meet", requires=["secret"]),
    ]
    report = analyze(make_graph("start", scenes))
    ce = violations_for(report, "meet")[0]["counterexample"]
    assert ce["length"] == 2
    assert ce["edge_indices"] == [0, 0]
    assert [hop["scene"] for hop in ce["route"]] == [
        "start",
        "lose_first",
        "meet",
    ]


def test_shorter_bad_path_wins_over_lexicographic(make_scene, make_graph, analyze):
    # 边序 [0,...] 的坏路更长；边序 [1,0] 的坏路更短——长度优先。
    scenes = [
        make_scene("start", adds=["secret"], targets=["long_keep", "drop"]),
        make_scene("long_keep", targets=["long_keep_2"]),
        make_scene("long_keep_2", removes=["secret"], targets=["meet"]),
        make_scene("drop", removes=["secret"], targets=["meet"]),
        make_scene("meet", requires=["secret"]),
    ]
    report = analyze(make_graph("start", scenes))
    ce = violations_for(report, "meet")[0]["counterexample"]
    assert ce["length"] == 2
    assert ce["edge_indices"] == [1, 0]


def test_counterexample_facts_are_replayed_along_route(
    make_scene, make_graph, analyze
):
    # 反例路线上的事实必须逐场景真实更新，而不是各分支并集。
    scenes = [
        make_scene(
            "start", adds=["secret", "map"], targets=["detour"]
        ),
        make_scene("detour", removes=["map"], adds=["key"], targets=["end"]),
        make_scene("end", requires=["secret", "map"]),
    ]
    report = analyze(make_graph("start", scenes))
    violations = violations_for(report, "end")
    by_fact = {v["fact"]: v["counterexample"] for v in violations}

    # secret 在唯一路径上始终成立 -> 无穿帮
    assert "secret" not in by_fact
    # map 被 detour 移除 -> 到达 end 时持有 secret 和 key，缺 map
    assert by_fact["map"]["arriving_facts"] == ["key", "secret"]
