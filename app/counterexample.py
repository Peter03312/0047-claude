"""穿帮反例回溯。

当事实 ``f`` 没有在目标场景 ``target`` 的所有前驱路径上成立时，
需要给出一条可复述的具体阅读路线：读者在这条路线的每一步如何
选择，到达 ``target`` 时持有哪些事实、缺了哪条 ``requires``。

裁决规则（题目要求）：
1. 最短反例优先——以边数（路径长度）比较；
2. 长度相同时按边序字典序比较——把路线上每条边在其前驱
   ``choices`` 中的下标组成序列，逐位比较，下标小者优先；
3. 严禁用各分支事实并集“拼”出一条不存在的路线，反例必须是
   真实存在的一条路径，沿途事实逐场景 removes/adds 真实更新。

实现方法：在显式状态图 ``(场景, 是否持有 f)`` 上做 BFS。同层内
按边序展开，BFS 第一次落到 ``target`` 且不持有 f 的状态，即为
最短、并列时边序最小的反例。其余事实随状态一并真实更新，
用于在报告里展示到达时的完整事实集。
"""

from collections import deque

from .models import Scene


class _State:
    __slots__ = ("scene", "has_f", "facts", "parent", "edge")

    def __init__(self, scene, has_f, facts, parent, edge):
        self.scene = scene
        self.has_f = has_f
        self.facts = facts
        self.parent = parent  # 前驱 _State，入口状态为 None
        self.edge = edge      # 从上一状态进入本状态所用的边下标


def _apply_update(scene: Scene, facts: frozenset[str]) -> frozenset[str]:
    """场景更新：先 removes 后 adds。"""
    return (facts - frozenset(scene.removes)) | frozenset(scene.adds)


def shortest_counterexample(
    graph_entry: str,
    scenes_by_id: dict[str, Scene],
    outgoing: dict[str, list[str]],
    target: str,
    fact: str,
) -> dict | None:
    """返回最短反例路线；若不存在（事实在所有路径上成立）返回 None。

    入口本身不会有反例：入口的事实由其 adds 注入，进入前为空，
    这是语义规定而非穿帮。
    """
    if target == graph_entry:
        return None

    entry_scene = scenes_by_id[graph_entry]
    entry_facts = frozenset(entry_scene.adds)  # removes 作用于空集，无效果
    start = _State(
        scene=graph_entry,
        has_f=fact in entry_facts,
        facts=entry_facts,
        parent=None,
        edge=None,
    )

    # 同一 (场景, has_f) 只需到达一次：BFS 保证首次到达就是最优路线，
    # 且边序展开保证并列时取到的是边序最小的路线。
    visited = {(start.scene, start.has_f)}
    queue = deque([start])

    while queue:
        state = queue.popleft()
        scene = scenes_by_id[state.scene]
        for edge_index, next_id in enumerate(outgoing.get(state.scene, ())):
            next_scene = scenes_by_id[next_id]
            # 进入 next_id 时持有的事实 = 当前场景更新后的事实。
            arrived_facts = _apply_update(scene, state.facts)
            next_has_f = fact in arrived_facts

            # 先判定：第一次以不持有 f 的状态抵达 target 就是答案。
            if next_id == target and not next_has_f:
                return _build_report(
                    target_state_scene=next_scene,
                    arrived_facts=arrived_facts,
                    parent_state=state,
                    edge_index=edge_index,
                    missing_fact=fact,
                )

            if (next_id, next_has_f) in visited:
                continue
            visited.add((next_id, next_has_f))
            queue.append(
                _State(
                    scene=next_id,
                    has_f=next_has_f,
                    facts=arrived_facts,
                    parent=state,
                    edge=edge_index,
                )
            )

    return None  # 所有到达 target 的路径都持有 f（理论上调用方不会走到这里）


def _build_report(
    target_state_scene: Scene,
    arrived_facts: frozenset[str],
    parent_state: _State,
    edge_index: int,
    missing_fact: str,
) -> dict:
    """从终止状态回溯出边序序列与完整场景路线。"""
    edge_indices: list[int] = []
    chain: list[_State] = []
    cur = parent_state
    while cur is not None:
        chain.append(cur)
        if cur.edge is not None:
            edge_indices.append(cur.edge)
        cur = cur.parent
    chain.reverse()
    edge_indices.reverse()
    edge_indices.append(edge_index)

    route_scenes = [state.scene for state in chain] + [target_state_scene.id]
    route = [
        {
            "scene": scene_id,
            "choice": choice,
        }
        for scene_id, choice in zip(route_scenes, [None, *edge_indices])
    ]

    return {
        "missing_fact": missing_fact,
        "length": len(edge_indices),
        "edge_indices": edge_indices,
        "route": route,
        "arriving_facts": sorted(arrived_facts),
    }
