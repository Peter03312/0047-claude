"""知识传播判定（must-facts 数据流，按真实状态推进）。

选择边可以带 ``available_when`` 条件：读者在出发场景完成
“先 removes 后 adds”更新后，必须持有条件中的全部事实，该选择才出现、
才可走。因此能否到达一个场景、到达时持有什么事实，都取决于读者一路
真实持有的事实集，而不再是无条件图上的单纯拓扑。

算法：在 ``(场景, 事实集)`` 状态空间里沿 DAG 拓扑序推进，事实集相同的
等价状态合并。对每个可达场景收集**所有可行路线**到达时的事实集：

- ``arriving_states[s]``：每条可行路线进入 s、执行 s 更新之前持有的
  事实集（等价状态已合并去重）。没有任何可行路线抵达的场景即为
  （条件意义上的）不可达场景。
- ``guaranteed_in[s]``：``arriving_states`` 中各事实集的**交集**——
  从入口到 s 的每一条**可行**读者路径都必然持有的事实。多条支线在
  这里取交集，绝不允许用各分支事实的并集放行——并集正是“凭空知情”
  穿帮的来源；被条件封闭的伪路线同样不得进入交集。
- ``guaranteed_out[s]``：s 按“先 removes 后 adds”更新后，所有可行
  路线上都必然持有的事实。

转移方程（DAG 上按拓扑序求解一次即可）::

    入口初始状态 = adds(entry)            # removes 作用于空集
    departing(s)  = (facts - removes(s)) ∪ adds(s)
    边 s -> t 开放 ⇔ available_when(边) ⊆ departing(s) 的事实
    in(t)         = ⋂ 所有开放边送达的 departing 事实集

入口自身的 ``requires`` 以空事实集检查（初始事实是 adds 注入的，
读者进入入口时尚未持有）。
"""

from collections.abc import Iterable

from .models import Scene


def apply_update(scene: Scene, facts: frozenset[str]) -> frozenset[str]:
    """场景更新：先 removes 后 adds，即 ``(facts - removes) ∪ adds``。"""

    return (facts - frozenset(scene.removes)) | frozenset(scene.adds)


def propagate_states(
    entry: str,
    order: list[str],
    scenes_by_id: dict[str, Scene],
) -> tuple[
    dict[str, set[frozenset[str]]],
    dict[str, frozenset[str]],
    dict[str, frozenset[str]],
]:
    """在 DAG 内按真实到达事实状态推进，合并等价状态。

    ``order`` 为（结构上可达的）场景拓扑序。条件边可能让某些场景在
    本步骤中仍无任何状态抵达，此时该场景不会出现在返回字典中。

    返回 ``(arriving_states, guaranteed_in, guaranteed_out)``：
    事实集均为 frozenset，防止下游分析意外修改传播结果。
    """
    arriving_states: dict[str, set[frozenset[str]]] = {
        entry: {frozenset()}
    }
    guaranteed_in: dict[str, frozenset[str]] = {}
    guaranteed_out: dict[str, frozenset[str]] = {}

    for sid in order:
        states = arriving_states.get(sid)
        if not states:
            # 该场景的所有入边在当时都不开放（或上游同样被封闭）：
            # 不产生任何状态，其下游也无法经它抵达。
            continue

        scene = scenes_by_id[sid]
        arriving = (
            frozenset.intersection(*states)
            if len(states) > 1
            else next(iter(states))
        )
        guaranteed_in[sid] = arriving
        # removes/adds 对所有路线一致，交集与更新可交换：
        # ⋂_i ((S_i - removes) ∪ adds) = (⋂_i S_i - removes) ∪ adds
        guaranteed_out[sid] = apply_update(scene, arriving)

        # 等价状态合并后再展开边：开放判定只依赖出发后的事实集。
        departing_states = {apply_update(scene, state) for state in states}
        for choice in scene.choices:
            conditions = frozenset(choice.available_when)
            for departed_facts in departing_states:
                if conditions and not conditions <= departed_facts:
                    continue  # 该路线上此选择尚未出现：边封闭，不可走
                arriving_states.setdefault(choice.target, set()).add(
                    departed_facts
                )

    return arriving_states, guaranteed_in, guaranteed_out


def missing_requirements(
    required: Iterable[str], guaranteed_in: frozenset[str]
) -> list[str]:
    """返回进入场景时未能在所有可行前驱路径上成立的要求（保持 requires 顺序）。"""
    return [fact for fact in required if fact not in guaranteed_in]
