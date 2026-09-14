"""FastAPI 交付层。

- POST /api/analyze ：接收故事图，返回知识连续性报告（200）；
  结构违规整单拒绝（422 + issue 列表）。
- GET  /healthz    ：容器健康检查 / Compose 冒烟探活用。
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .errors import GraphValidationError
from .models import StoryGraph
from .service import analyze_graph

app = FastAPI(
    title="知识连续性 API",
    description=(
        "检查多视角校园故事图：汇合场景要求的事实，是否在每一条"
        "读者路径上都成立。禁止用各分支事实并集放行穿帮。"
    ),
    version="1.0.0",
)


@app.exception_handler(GraphValidationError)
async def graph_validation_error_handler(
    request: Request, exc: GraphValidationError
) -> JSONResponse:
    # 领域结构错误（环、悬空引用、增删同一事实等）：整单拒绝。
    return JSONResponse(
        status_code=422,
        content={
            "ok": False,
            "error": "graph_validation_failed",
            "issues": exc.issues,
        },
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Pydantic 形状错误同样整单拒绝，保留 FastAPI 原生 loc/msg 定位信息。
    return JSONResponse(
        status_code=422,
        content={
            "ok": False,
            "error": "invalid_request",
            "issues": exc.errors(),
        },
    )


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True, "service": "knowledge-continuity"}


@app.post("/api/analyze")
async def analyze(graph: StoryGraph) -> dict:
    return analyze_graph(graph)
