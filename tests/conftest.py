"""pytest 公共辅助：用简短的构造式写法搭故事图。"""

import pytest

from app.models import Choice, Scene, StoryGraph
from app.service import analyze_graph


@pytest.fixture
def make_scene():
    def _make(
        sid,
        adds=(),
        removes=(),
        requires=(),
        targets=(),
        edge_when=None,
    ):
        """搭一个场景。

        ``targets`` 仍是目标 id 列表（边序）；``edge_when`` 可选，形如
        ``{边下标: [条件事实, ...]}``，给指定选择挂 ``available_when``。
        """
        edge_when = edge_when or {}
        return Scene(
            id=sid,
            adds=list(adds),
            removes=list(removes),
            requires=list(requires),
            choices=[
                Choice(
                    target=t,
                    available_when=list(edge_when.get(i, ())),
                )
                for i, t in enumerate(targets)
            ],
        )

    return _make


@pytest.fixture
def make_graph():
    def _make(entry, scenes):
        return StoryGraph(entry=entry, scenes=scenes)

    return _make


@pytest.fixture
def analyze():
    def _analyze(graph):
        return analyze_graph(graph)

    return _analyze


def scene_report(report: dict, scene_id: str) -> dict:
    return next(s for s in report["scenes"] if s["id"] == scene_id)


def violations_for(report: dict, scene_id: str) -> list[dict]:
    return [v for v in report["violations"] if v["scene"] == scene_id]
