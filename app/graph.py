"""图层面的结构校验与遍历原语。

整单拒绝的硬性规则都在这里（不满足就不允许进入知识传播分析）：
1. 场景 id 必须唯一；
2. ``entry`` 必须指向存在的场景；
3. 每条边的 target 必须存在（悬空引用）；
4. 同一场景不得对同一事实既 adds 又 removes；
5. 边构成有向无环图（检测到环即拒绝，并回环的场景序列）。
"""

from collections import defaultdict, deque

from .errors import GraphValidationError
from .models import StoryGraph


def _find_cycle(
    scene_ids: list[str],
    outgoing: dict[str, list[str]],
) -> list[str] | None:
    """迭代版三色 DFS 找环；返回环上场景 id 序列（首尾同 id）。"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {sid: WHITE for sid in scene_ids}
    parent: dict[str, str | None] = {sid: None for sid in scene_ids}

    for root in scene_ids:  # 按输入顺序选根，输出稳定
        if color[root] != WHITE:
            continue
        color[root] = GRAY
        stack = [iter(outgoing.get(root, ()))]
        on_path = [root]
        while stack:
            nxt = next(stack[-1], None)
            if nxt is None:
                color[on_path.pop()] = BLACK
                stack.pop()
                continue
            if color[nxt] == GRAY:
                # nxt 是当前路径上的祖先，环的方向必须与边一致，
                # 即 nxt 沿当前 DFS 路径下行再经当前边回到 nxt：
                # on_path[i+1:] 已是“环首之后 -> 当前 DFS 节点”的正向
                # 顺序，绝不能反转（否则会拼出图中不存在的边）。
                cycle = [nxt]
                i = len(on_path) - 1
                while on_path[i] != nxt:
                    i -= 1
                cycle.extend(on_path[i + 1 :])
                cycle.append(nxt)
                return cycle
            if color[nxt] == WHITE:
                parent[nxt] = on_path[-1]
                color[nxt] = GRAY
                on_path.append(nxt)
                stack.append(iter(outgoing.get(nxt, ())))
    return None


def validate_structure(graph: StoryGraph) -> tuple[dict[str, int], dict[str, list[str]]]:
    """执行全部结构规则；有任何问题抛 ``GraphValidationError``（整单拒绝）。

    返回 ``(id -> 在 scenes 中的下标, id -> 按边序排列的 target 列表)``。
    """
    issues: list[dict] = []

    index_of: dict[str, int] = {}
    for i, scene in enumerate(graph.scenes):
        if scene.id in index_of:
            issues.append(
                {
                    "code": "duplicate_scene",
                    "scene": scene.id,
                    "message": f"场景 id 重复：{scene.id}",
                }
            )
        else:
            index_of[scene.id] = i

    if graph.entry not in index_of:
        issues.append(
            {
                "code": "unknown_entry",
                "scene": graph.entry,
                "message": f"入口场景不存在：{graph.entry}",
            }
        )

    outgoing: dict[str, list[str]] = defaultdict(list)
    for scene in graph.scenes:
        if scene.id not in index_of:
            continue  # 重复 id 的副本不再参与后续检查
        for edge_index, choice in enumerate(scene.choices):
            if choice.target not in index_of:
                issues.append(
                    {
                        "code": "dangling_edge",
                        "scene": scene.id,
                        "edge": edge_index,
                        "target": choice.target,
                        "message": (
                            f"场景 {scene.id} 的第 {edge_index} 条选择"
                            f"指向不存在的场景：{choice.target}"
                        ),
                    }
                )
            outgoing[scene.id].append(choice.target)

        overlap = sorted(set(scene.adds) & set(scene.removes))
        for fact in overlap:
            issues.append(
                {
                    "code": "add_remove_same_fact",
                    "scene": scene.id,
                    "fact": fact,
                    "message": f"场景 {scene.id} 对同一事实既添加又移除：{fact}",
                }
            )

    # 前面的错误会让环检测没有意义（缺节点 / 重复节点），有则直接拒绝。
    if not issues:
        cycle = _find_cycle(list(index_of.keys()), outgoing)
        if cycle is not None:
            issues.append(
                {
                    "code": "cycle_detected",
                    "cycle": cycle,
                    "message": "故事图存在环：" + " -> ".join(cycle),
                }
            )

    if issues:
        raise GraphValidationError(issues)

    return index_of, dict(outgoing)


def reachable_scenes(entry: str, outgoing: dict[str, list[str]]) -> set[str]:
    """结构可达集合：沿所有边（忽略 ``available_when``）从入口可达的场景。

    这是第一层可达性，用于限定拓扑序与传播的分析范围；条件边是否真正
    可走由 ``propagation.propagate_states`` 按真实事实状态再判定。
    """
    seen = {entry}
    queue = deque([entry])
    while queue:
        sid = queue.popleft()
        for target in outgoing.get(sid, ()):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def topo_order(
    scene_ids: list[str],
    outgoing: dict[str, list[str]],
) -> tuple[list[str], dict[str, list[tuple[str, int]]]]:
    """可达子图上的 Kahn 拓扑序（保留输入/边序），同时返回前驱表。

    调用前应已通过结构校验（无环）。``incoming[u]`` 为
    ``(前驱场景 id, 该边在前驱 choices 中的下标)``，按前驱 id 的输入
    顺序排列。
    """
    indegree = {sid: 0 for sid in scene_ids}
    incoming: dict[str, list[tuple[str, int]]] = {sid: [] for sid in scene_ids}
    for sid in scene_ids:
        for edge_index, target in enumerate(outgoing.get(sid, ())):
            if target in indegree:
                indegree[target] += 1
                incoming[target].append((sid, edge_index))

    # 按输入顺序入队，拓扑序对相同输入保持确定。
    ready = deque(sid for sid in scene_ids if indegree[sid] == 0)
    order: list[str] = []
    while ready:
        sid = ready.popleft()
        order.append(sid)
        for target in outgoing.get(sid, ()):
            if target in indegree:
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)

    if len(order) != len(scene_ids):  # 理论不可达：结构校验已保证无环
        raise GraphValidationError(
            [{"code": "cycle_detected", "message": "可达子图中检测到环"}]
        )
    return order, incoming
