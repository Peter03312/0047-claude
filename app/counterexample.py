"""穿帮反例回溯。

当事实 ``f`` 没有在目标场景 ``target`` 的所有**可行**前驱路径上成立时，
需要给出一条可复述的具体阅读路线：读者在这条路线的每一步如何
选择（只选当时已经出现、即 ``available_when`` 全部满足的选择），到达
``target`` 时持有哪些事实、缺了哪条 ``requires``。

裁决规则（题目要求）：
1. 最短反例优先——以边数（路径长度）比较；
2. 长度相同时按边序字典序比较——把路线上每条边在其前驱
   ``choices`` 中的下标组成序列，逐位比较，下标小者优先；
3. 严禁用各分支事实并集“拼”出一条不存在的路线，反例必须是
   真实存在且边当时可用的一条路径，沿途事实逐场景 removes/adds
   真实更新。

实现方法：在显式状态图 ``(场景, 完整事实集)`` 上做 BFS（事实集相同的
等价状态合并）。只穿过出发场景更新后条件全部满足的选择；同层内按
边序展开，BFS 第一次落到 ``target`` 且不持有 f 的状态，即为最短、
并列时边序最小的反例。其余事实随状态一并真实更新，用于在报告里
展示到达时的完整事实集。
"""

from collections import deque

from .models import Scene
from .propagation import apply_update


class _State:
    __slots__ = ("scene", "facts", "parent", "edge")

    def __init__(self, scene, facts, parent, edge):
        self.scene = scene
        self.facts = facts
        self.parent = parent  # 前驱 _State，入口状态为 None
        self.edge = edge      # 从上一状态进入本状态所用的边下标


def shortest_counterexample(
    graph_entry: str,
    scenes_by_id: dict[str, Scene],
    target: str,
    fact: str,
) -> dict | None:
    """返回最短反例路线；若不存在（事实在所有可行路径上成立）返回 None。

    只穿过当时开放的选择（``available_when`` 条件在出发场景更新后
    全部满足）。入口本身不会有反例：入口的事实由其 adds 注入，进入前
    为空，这是语义规定而非穿帮。
    """
    if target == graph_entry:
        return None

    entry_scene = scenes_by_id[graph_entry]
    entry_facts = apply_update(entry_scene, frozenset())  # 即入口的 adds
    start = _State(
        scene=graph_entry,
        facts=entry_facts,
        parent=None,
        edge=None,
    )

    # 同一 (场景, 完整事实集) 只需到达一次：事实集相同意味着后续开放边
    # 与到达事实完全一致，属等价状态。BFS 保证首次到达就是最优路线，
    # 且边序展开保证并列时取到的是边序最小的路线。
    visited = {(start.scene, start.facts)}
    queue = deque([start])

    while queue:
        state = queue.popleft()
        scene = scenes_by_id[state.scene]
        # 边开放判定看“出发场景更新之后”的事实集。
        departed_facts = apply_update(scene, state.facts)
        for edge_index, choice in enumerate(scene.choices):
            conditions = frozenset(choice.available_when)
            if conditions and not conditions <= departed_facts:
                continue  # 该选择此时尚未出现：封闭边，反例不得穿过
            next_id = choice.target
            next_scene = scenes_by_id[next_id]
            # 进入 next_id 时持有的事实 = 当前场景更新后的事实。
            arrived_facts = departed_facts

            # 先判定：第一次以不持有 f 的状态抵达 target 就是答案。
            if next_id == target and fact not in arrived_facts:
                return _build_report(
                    target_scene=next_scene,
                    arrived_facts=arrived_facts,
                    parent_state=state,
                    edge_index=edge_index,
                    missing_fact=fact,
                )

            if (next_id, arrived_facts) in visited:
                continue
            visited.add((next_id, arrived_facts))
            queue.append(
                _State(
                    scene=next_id,
                    facts=arrived_facts,
                    parent=state,
                    edge=edge_index,
                )
            )

    return None  # 所有到达 target 的可行路径都持有 f（调用方不应走到这里）


def _build_report(
    target_scene: Scene,
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

    route_scenes = [state.scene for state in chain] + [target_scene.id]
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
