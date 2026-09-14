"""领域错误：图通过了 Pydantic 形状校验，但违反故事结构规则。

这类错误会被 HTTP 层统一翻译成 422，并携带可定位的 issue 列表，
实现“整单拒绝”——不返回任何半截分析结果。
"""


class GraphValidationError(Exception):
    def __init__(self, issues: list[dict]):
        self.issues = issues
        super().__init__(f"故事图结构校验失败，共 {len(issues)} 处问题")
