"""条件选择 ``available_when``：只有读者已持有所需事实时边才出现。

契约：
- 缺省/空列表 = 无条件开放（旧图结果不变由既有测试保证）；
- 分析只沿当时开放的边推进，等价状态合并，据此计算可达性与
  “进入场景时保证事实”；
- 被条件封闭的路线既不得制造伪穿帮，也不得参与保证事实的交集；
- 选择只在部分路线开放时，反例仍只能穿过可用边，取最短可行路线，
  并列时按边序裁决；
- 所有入边都封闭的目标进入不可达清单，不产生 requires 违规。
"""

from conftest import scene_report, violations_for


def test_condition_excludes_pseudo_counterexample(
    make_scene, make_graph, analyze
):
    # 核心回归：走廊支线会丢秘密，但它进入汇合点的选择只有“知道秘密”
    # 时才出现——不知道秘密的读者根本走不到汇合点，不得据此误报穿帮。
    scenes = [
        make_scene(
            "start",
            adds=["secret"],
            targets=["rooftop", "corridor"],
        ),
        make_scene("rooftop", targets=["meet"]),
        make_scene(
            "corridor",
            removes=["secret"],
            targets=["meet"],
            edge_when={0: ["secret"]},  # 丢了秘密 -> 这条选择不出现
        ),
        make_scene("meet", requires=["secret"]),
    ]
    report = analyze(make_graph("start", scenes))

    assert report["violated"] is False
    assert violations_for(report, "meet") == []
    assert report["unreachable_scenes"] == []
    meet = scene_report(report, "meet")
    assert meet["reachable"] is True
    # 唯一可行路线（天台支）始终持有秘密。
    assert meet["guaranteed_facts_on_entry"] == ["secret"]
    assert meet["requires"][0]["satisfied"] is True
    assert meet["requires"][0]["counterexample"] is None


def test_closed_route_is_excluded_from_guaranteed_intersection(
    make_scene, make_graph, analyze
):
    # 封闭支线独有的事实不得混入保证事实；开放支线的事实正常保留。
    scenes = [
        make_scene(
            "start", adds=["secret"], targets=["branch_bad", "branch_ok"]
        ),
        # 坏支线：丢掉秘密还拿到 note，但通往 meet 的选择要求秘密 -> 封闭
        make_scene(
            "branch_bad",
            removes=["secret"],
            adds=["note"],
            targets=["meet"],
            edge_when={0: ["secret"]},
        ),
        # 好支线：拿到 token，无条件汇合
        make_scene("branch_ok", adds=["token"], targets=["meet"]),
        make_scene("meet"),
    ]
    report = analyze(make_graph("start", scenes))

    meet = scene_report(report, "meet")
    assert meet["reachable"] is True
    assert meet["guaranteed_facts_on_entry"] == ["secret", "token"]
    assert meet["guaranteed_facts_after_update"] == ["secret", "token"]


def test_shortest_feasible_counterexample_skips_closed_shortcut(
    make_scene, make_graph, analyze
):
    # 长度 2 的坏路 [0,0] 在第二跳要求秘密（已被移除）-> 封闭；
    # 唯一可行坏路是长度 3 的 [1,0,0]，必须返回它而不是更短的伪路线。
    scenes = [
        make_scene(
            "start", adds=["secret"], targets=["fast_lose", "keep_branch"]
        ),
        make_scene(
            "fast_lose",
            removes=["secret"],
            targets=["meet"],
            edge_when={0: ["secret"]},  # 秘密已丢，捷径封闭
        ),
        make_scene("keep_branch", targets=["slow_lose"]),
        make_scene("slow_lose", removes=["secret"], targets=["meet"]),
        make_scene("meet", requires=["secret"]),
    ]
    report = analyze(make_graph("start", scenes))

    ce = violations_for(report, "meet")[0]["counterexample"]
    assert ce["length"] == 3
    assert ce["edge_indices"] == [1, 0, 0]
    assert [hop["scene"] for hop in ce["route"]] == [
        "start",
        "keep_branch",
        "slow_lose",
        "meet",
    ]
    assert ce["arriving_facts"] == []


def test_tie_among_feasible_bad_routes_still_breaks_by_edge_order(
    make_scene, make_graph, analyze
):
    # 两条等长坏路：[0,0] 的第二跳要求秘密（已丢）而封闭，
    # 只剩 [1,0] 可行且仍坏 -> 取 [1,0]。
    scenes = [
        make_scene(
            "start", adds=["secret"], targets=["lose_first", "lose_second"]
        ),
        make_scene(
            "lose_first",
            removes=["secret"],
            targets=["meet"],
            edge_when={0: ["secret"]},
        ),
        make_scene("lose_second", removes=["secret"], targets=["meet"]),
        make_scene("meet", requires=["secret"]),
    ]
    report = analyze(make_graph("start", scenes))
    ce = violations_for(report, "meet")[0]["counterexample"]
    assert ce["length"] == 2
    assert ce["edge_indices"] == [1, 0]


def test_choice_open_on_some_states_merges_equivalent_states(
    make_scene, make_graph, analyze
):
    # 同一选择在一种事实状态下开放、另一种封闭，但两条开放路线事实
    # 等价时必须合并：汇合点保证事实 = 两可行路线的交集。
    scenes = [
        make_scene(
            "start", adds=["secret", "map"], targets=["path_a", "path_b"]
        ),
        # A 支丢 map 后仍可走（边只要 secret）；
        make_scene(
            "path_a",
            removes=["map"],
            targets=["join"],
            edge_when={0: ["secret"]},
        ),
        # B 支原样汇合（无条件边）。
        make_scene("path_b", targets=["join"]),
        make_scene("join", requires=["secret"]),
    ]
    report = analyze(make_graph("start", scenes))

    assert report["violated"] is False
    join = scene_report(report, "join")
    # map 只在 B 支成立，交集里不能有；secret 两支都在。
    assert join["guaranteed_facts_on_entry"] == ["secret"]


def test_fully_closed_target_is_unreachable_without_violation(
    make_scene, make_graph, analyze
):
    # sink 的两条入边分别要求从未出现过的事实 -> 全封闭；
    # 即使 sink 要求 secret，也只能进不可达清单，不得产生违规。
    scenes = [
        make_scene("start", adds=["secret"], targets=["via_a", "via_b"]),
        make_scene(
            "via_a", targets=["sink"], edge_when={0: ["never_a"]}
        ),
        make_scene(
            "via_b", targets=["sink"], edge_when={0: ["never_b"]}
        ),
        make_scene("sink", requires=["secret"]),
    ]
    report = analyze(make_graph("start", scenes))

    assert report["violated"] is False
    assert report["violations"] == []
    assert report["unreachable_scenes"] == ["sink"]
    assert scene_report(report, "sink") == {"id": "sink", "reachable": False}
    assert report["summary"]["reachable_scenes"] == 3
    assert report["summary"]["unreachable_scenes"] == 1


def test_downstream_of_only_closed_route_is_also_unreachable(
    make_scene, make_graph, analyze
):
    # gate 场景先 removes key 再 adds badge：
    # 要 key 的边在更新后判定 -> 封闭；其下游 deeper 不可另路抵达。
    scenes = [
        make_scene("start", adds=["key"], targets=["gate"]),
        make_scene(
            "gate",
            removes=["key"],
            adds=["badge"],
            targets=["needs_key", "needs_badge"],
            edge_when={0: ["key"], 1: ["badge"]},
        ),
        # needs_key 即使要求事实也不能算穿帮：读者走不进来。
        make_scene("needs_key", requires=["key"], targets=["deeper"]),
        make_scene("deeper"),
        make_scene("needs_badge"),
    ]
    report = analyze(make_graph("start", scenes))

    assert report["violated"] is False
    # 不可达清单按投稿（输入）顺序稳定排列：needs_key 先于 deeper。
    assert report["unreachable_scenes"] == ["needs_key", "deeper"]
    badge_scene = scene_report(report, "needs_badge")
    assert badge_scene["reachable"] is True
    # gate 先 removes key 后 adds badge，开放边送达的事实只有 badge。
    assert badge_scene["guaranteed_facts_on_entry"] == ["badge"]


def test_entry_edge_gated_on_entry_adds(make_scene, make_graph, analyze):
    # 入口选择在入口完成 adds 更新后判定：要求到初始事实即开放。
    scenes = [
        make_scene(
            "start",
            adds=["secret"],
            targets=["open_room", "locked_room"],
            edge_when={1: ["missing"]},
        ),
        make_scene("open_room"),
        make_scene("locked_room", requires=["secret"]),
    ]
    report = analyze(make_graph("start", scenes))

    assert report["violated"] is False
    assert report["unreachable_scenes"] == ["locked_room"]
    assert scene_report(report, "open_room")["reachable"] is True


def test_conditional_edges_still_undergo_structure_validation(
    make_scene, make_graph
):
    # 条件边仍是图的边：悬空引用 / 环等结构规则照旧整单拒绝，
    # 不因“边可能不开放”而豁免。
    from app.errors import GraphValidationError
    from app.service import analyze_graph

    scenes = [
        make_scene(
            "start",
            adds=["secret"],
            targets=["ghost"],
            edge_when={0: ["secret"]},
        ),
    ]
    try:
        analyze_graph(make_graph("start", scenes))
    except GraphValidationError as exc:
        assert [i["code"] for i in exc.issues] == ["dangling_edge"]
        issue = exc.issues[0]
        assert issue["scene"] == "start"
        assert issue["edge"] == 0
    else:  # pragma: no cover
        raise AssertionError("条件悬空边必须整单拒绝")


def test_conditional_cycle_is_still_rejected(make_scene, make_graph):
    from app.errors import GraphValidationError
    from app.service import analyze_graph

    scenes = [
        make_scene(
            "a", adds=["x"], targets=["b"], edge_when={0: ["x"]}
        ),
        make_scene("b", targets=["c"]),
        make_scene("c", targets=["a"]),
    ]
    try:
        analyze_graph(make_graph("a", scenes))
    except GraphValidationError as exc:
        assert [i["code"] for i in exc.issues] == ["cycle_detected"]
    else:  # pragma: no cover
        raise AssertionError("穿过条件边的环仍必须整单拒绝")
