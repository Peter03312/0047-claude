"""知识传播判定（must-facts 数据流）。

对每个可达场景计算两个集合：

- ``guaranteed_in[s]``：**从入口到 s 的每一条读者路径**，在进入 s、
  执行 s 的更新之前，都必然持有的事实。多条支线在这里取交集，
  绝不允许用各分支事实的并集放行——并集正是“凭空知情”穿帮的来源。
- ``guaranteed_out[s]``：s 按“先 removes 后 adds”更新之后，所有
  路径上都必然持有的事实。

转移方程（DAG 上按拓扑序求解一次即可）::

    in(entry)  = ∅                         # 入口的初始事实由 adds 注入
    in(s)      = ⋂ predecessors(p).out     # 只有一个入口，所有路径必经这些前驱
    out(s)     = (in(s) - removes(s)) ∪ adds(s)

入口自身的 ``requires`` 以空事实集检查（初始事实是 adds 注入的，
读者进入入口时尚未持有）。
"""

from collections.abc import Iterable

from .models import Scene


def propagate_must_facts(
    entry: str,
    order: list[str],
    incoming: dict[str, list[tuple[str, int]]],
    scenes_by_id: dict[str, Scene],
) -> tuple[dict[str, frozenset[str]], dict[str, frozenset[str]]]:
    """按拓扑序计算每个可达场景的 guaranteed_in / guaranteed_out。

    返回的集合是 frozenset，防止下游分析意外修改传播结果。
    """
    guaranteed_in: dict[str, frozenset[str]] = {}
    guaranteed_out: dict[str, frozenset[str]] = {}

    for sid in order:
        scene = scenes_by_id[sid]
        if sid == entry:
            arriving: frozenset[str] = frozenset()
        else:
            preds = incoming[sid]
            # 取所有前驱 out 的交集。可达子图中每个非入口节点至少有一个
            # 可达前驱；多个前驱（菱形汇合）在此刻发生，交集而非并集。
            arriving = frozenset.intersection(
                *(guaranteed_out[p] for p, _ in preds)
            )
        guaranteed_in[sid] = arriving
        guaranteed_out[sid] = frozenset(
            (arriving - frozenset(scene.removes)) | frozenset(scene.adds)
        )

    return guaranteed_in, guaranteed_out


def missing_requirements(
    required: Iterable[str], guaranteed_in: frozenset[str]
) -> list[str]:
    """返回进入场景时未能在所有前驱路径上成立的要求（保持 requires 顺序）。"""
    return [fact for fact in required if fact not in guaranteed_in]
