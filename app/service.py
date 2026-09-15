"""分析编排：结构校验 -> 可达性 -> 状态空间传播 -> 反例回溯。

可达性分两层：

1. **结构可达**：沿所有边（忽略 ``available_when``）从入口能到达的
   场景。不可达场景仅列出，不参与判定，拓扑序也只在这层上求。
2. **条件可达**：在结构可达子图内，按读者真实持有的事实状态推进，
   只有开放边（出发场景“先 removes 后 adds”更新后条件事实全部成立）
   能送达状态。若一个场景的所有入边都因条件不满足而封闭，它连同其
   无法另路抵达的下游一起进入不可达清单，且**不产生 requires 违规**。

报告字段全部可定位到场景、事实和具体反例路线；集合一律排序、
场景与要求保持输入顺序，保证同一输入永远得到同一输出。
"""

from .counterexample import shortest_counterexample
from .graph import (
    reachable_scenes,
    topo_order,
    validate_structure,
)
from .models import StoryGraph
from .propagation import missing_requirements, propagate_states


def analyze_graph(graph: StoryGraph) -> dict:
    # 1) 整单拒绝：环 / 悬空引用 / 同场景增删同一事实等。
    index_of, outgoing = validate_structure(graph)
    scenes_by_id = {scene.id: scene for scene in graph.scenes}

    # 2) 结构可达子图（忽略边条件）：拓扑序只在这层上求。
    structural_reachable = reachable_scenes(graph.entry, outgoing)
    structural_in_input_order = [
        scene.id
        for scene in graph.scenes
        if scene.id in structural_reachable
    ]
    order, _incoming = topo_order(structural_in_input_order, outgoing)

    # 3) 在 DAG 内按真实到达事实状态推进、合并等价状态：
    #    只走当时开放的选择，据此确定真正可达场景与进入时保证事实。
    arriving_states, guaranteed_in, guaranteed_out = propagate_states(
        graph.entry, order, scenes_by_id
    )
    reachable = set(arriving_states)
    unreachable = [
        scene.id for scene in graph.scenes if scene.id not in reachable
    ]

    scene_reports: list[dict] = []
    violations: list[dict] = []

    # 场景按投稿（输入）顺序汇报，方便小作者对照原稿。
    for scene in graph.scenes:
        if scene.id not in reachable:
            # 结构上孤立，或所有入边都被 available_when 封闭：
            # 只列出，不判定 requires。
            scene_reports.append({"id": scene.id, "reachable": False})
            continue

        arriving = guaranteed_in[scene.id]
        requires_report = []
        for fact in scene.requires:
            satisfied = fact in arriving
            counterexample = None
            if not satisfied:
                if scene.id == graph.entry:
                    # 入口没有任何前驱路线：初始事实由 adds 注入，
                    # 进入入口前读者为空手，长度 0 即反例。
                    counterexample = {
                        "missing_fact": fact,
                        "length": 0,
                        "edge_indices": [],
                        "route": [{"scene": graph.entry, "choice": None}],
                        "arriving_facts": [],
                    }
                else:
                    counterexample = shortest_counterexample(
                        graph.entry,
                        scenes_by_id,
                        scene.id,
                        fact,
                    )
                violations.append(
                    {
                        "scene": scene.id,
                        "fact": fact,
                        "counterexample": counterexample,
                    }
                )
            requires_report.append(
                {
                    "fact": fact,
                    "satisfied": satisfied,
                    "counterexample": counterexample,
                }
            )

        # requires_report 必须与传播判定（集合视图）一致。
        assert {
            item["fact"] for item in requires_report if not item["satisfied"]
        } == set(missing_requirements(scene.requires, arriving))

        scene_reports.append(
            {
                "id": scene.id,
                "reachable": True,
                "guaranteed_facts_on_entry": sorted(arriving),
                "guaranteed_facts_after_update": sorted(
                    guaranteed_out[scene.id]
                ),
                "requires": requires_report,
            }
        )

    return {
        "entry": graph.entry,
        "violated": bool(violations),
        "summary": {
            "total_scenes": len(graph.scenes),
            "reachable_scenes": len(reachable),
            "unreachable_scenes": len(unreachable),
            "violations": len(violations),
        },
        "unreachable_scenes": unreachable,
        "scenes": scene_reports,
        "violations": violations,
    }
