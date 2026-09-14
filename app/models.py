"""故事图的 Pydantic 模型。

输入语义：
- ``entry`` 指向唯一入口场景；入口场景的 ``adds`` 即故事的初始事实，
  读者从入口出发时自动持有。
- 每个场景按“先 removes 后 adds”更新事实集合。
- ``requires`` 列出进入该场景（发生更新之前）必须成立的事实。
- ``choices`` 是读者可选的出口边，**输入顺序即边序**，用于并列反例的
  确定性裁决，不得重排。
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# 场景 id 与事实名都不允许为空白字符串；首尾空白视作笔误，统一裁掉。
NonEmptyText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1)
]


def _dedupe_keep_order(items: list[str]) -> list[str]:
    """按首次出现去重，保留输入顺序（稳定输出的基础之一）。"""
    return list(dict.fromkeys(items))


class Choice(BaseModel):
    """一条读者选择边。"""

    model_config = ConfigDict(extra="forbid")

    target: NonEmptyText
    label: str | None = None


class Scene(BaseModel):
    """一个故事场景。"""

    model_config = ConfigDict(extra="forbid")

    id: NonEmptyText
    adds: list[NonEmptyText] = Field(default_factory=list)
    removes: list[NonEmptyText] = Field(default_factory=list)
    requires: list[NonEmptyText] = Field(default_factory=list)
    choices: list[Choice] = Field(default_factory=list)

    @model_validator(mode="after")
    def _drop_duplicate_facts(self) -> "Scene":
        # 同一事实在同一栏重复书写不改变语义，按首现去重，保证报告稳定。
        self.adds = _dedupe_keep_order(self.adds)
        self.removes = _dedupe_keep_order(self.removes)
        self.requires = _dedupe_keep_order(self.requires)
        return self


class StoryGraph(BaseModel):
    """一次投稿：有限有向图 + 唯一入口。"""

    model_config = ConfigDict(extra="forbid")

    entry: NonEmptyText
    scenes: list[Scene] = Field(min_length=1)
