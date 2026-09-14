# 知识连续性 API（Knowledge Continuity API）

一个纯后端服务，面向多视角校园故事合写社团：检查汇合后的公共场景里，
某个角色会不会**凭空知道**只有其他支线才得知的秘密。

典型穿帮：晓雯支线的读者在天台得知了秘密，另一条走廊支线的读者并不知道；
汇合后的公共场景却让两条支线的角色都提起这个秘密。本服务会给出一条
**可以照着走一遍的具体阅读路线**，让小作者在交换稿件前就能定位穿帮。

## 核心规则

投稿是一张**有限有向无环图（DAG）**：

- `entry`：唯一入口场景；入口场景的 `adds` 即故事的**初始事实**，
  读者从入口出发时自动持有。
- 每个场景按 **先 `removes` 后 `adds`** 更新事实集合
  （`(事实集 - removes) ∪ adds`）。
- `requires`：进入该场景（发生更新之前）必须成立的事实。
- `choices`：读者可选的出口边，**输入顺序就是边序**，用于并列反例的裁决。

判定规则（关键）：

1. **只分析从入口可达的场景**；不可达场景仅在报告中列出，不参与判定。
2. 某个 `requires` 事实，必须在**从入口到该场景的每一条前驱路径**上都成立。
   多条支线在此取事实**交集**——**禁止用各分支事实的并集放行**，
   并集正是“凭空知情”的来源。
3. 存在不成立的路径时，返回**最短反例**：
   - 先比路径长度（边数）；
   - 长度相同时，把路线上每条边在其 `choices` 中的下标组成序列，
     按字典序取最小（边序最小）的一条；
   - 反例是真实存在的一条读者路线，沿途事实逐场景真实更新，
     不是各分支拼出来的。
4. **整单拒绝**（HTTP 422，不出半截报告）：
   - 图中存在环（含自环）；
   - 边指向不存在的场景（悬空引用）；
   - 同一场景对同一事实既 `adds` 又 `removes`；
   - 场景 id 重复；`entry` 指向不存在的场景；请求体不符合模型。
5. 同一输入输出稳定：集合一律排序，场景与 `requires` 保持投稿顺序。

> 入口自身的 `requires` 在初始事实注入（入口的 `adds`）之前检查，
> 因此入口要求的任何事实都视为缺失，对应长度为 0 的反例。

## 接口

### `GET /healthz`

存活/健康检查。

### `POST /api/analyze`

请求体：

```json
{
  "entry": "start",
  "scenes": [
    {
      "id": "start",
      "adds": ["secret"],
      "removes": [],
      "requires": [],
      "choices": [
        {"target": "branch_a", "label": "走天台"},
        {"target": "branch_b", "label": "走走廊"}
      ]
    },
    {"id": "branch_a", "choices": [{"target": "meet"}]},
    {"id": "branch_b", "removes": ["secret"], "choices": [{"target": "meet"}]},
    {"id": "meet", "requires": ["secret"]}
  ]
}
```

成功响应（200，节选）：

```json
{
  "entry": "start",
  "violated": true,
  "summary": {"total_scenes": 4, "reachable_scenes": 4, "unreachable_scenes": 0, "violations": 1},
  "unreachable_scenes": [],
  "scenes": [
    {
      "id": "meet",
      "reachable": true,
      "guaranteed_facts_on_entry": [],
      "guaranteed_facts_after_update": [],
      "requires": [
        {
          "fact": "secret",
          "satisfied": false,
          "counterexample": {
            "missing_fact": "secret",
            "length": 2,
            "edge_indices": [1, 0],
            "route": [
              {"scene": "start", "choice": null},
              {"scene": "branch_b", "choice": 1},
              {"scene": "meet", "choice": 0}
            ],
            "arriving_facts": []
          }
        }
      ]
    }
  ],
  "violations": [
    {"scene": "meet", "fact": "secret", "counterexample": { "...": "同上" }}
  ]
}
```

读法：走走廊的读者（在 `start` 选第 **1** 条边，再在 `branch_b` 选第 **0** 条）
到达 `meet` 时秘密已被移除，所以 `meet` 不能把这个秘密当成公共知识。

整单拒绝（422）：

```json
{
  "ok": false,
  "error": "graph_validation_failed",
  "issues": [
    {"code": "dangling_edge", "scene": "start", "edge": 1, "target": "ghost", "message": "..."}
  ]
}
```

结构问题 code：`cycle_detected`、`dangling_edge`、`add_remove_same_fact`、
`duplicate_scene`、`unknown_entry`；请求体形状错误为 `error: invalid_request`。

完整中文示例见 [`examples/diamond_story.json`](examples/diamond_story.json)。

## 模块划分

| 文件 | 职责 |
| --- | --- |
| `app/models.py` | Pydantic 图模型（场景、边、事实），输入顺序即边序 |
| `app/graph.py` | 结构校验（环/悬空/增删冲突）、可达性、拓扑序 |
| `app/propagation.py` | must-facts 数据流：所有前驱路径取交集，禁止并集放行 |
| `app/counterexample.py` | 显式状态图 BFS：最短 + 边序最小反例回溯 |
| `app/service.py` | 编排分析、生成可定位的稳定 JSON 报告 |
| `app/main.py` | FastAPI 交付（`/api/analyze`、`/healthz`、422 处理） |
| `scripts/smoke.py` | 一次性 HTTP 冒烟（标准库实现） |
| `tests/` | pytest：菱形汇合、移除后再使用、不可达、并列反例、结构拒绝、HTTP |

## 本地运行（不使用 Docker）

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q                      # 单元 + HTTP 测试
python3 -m uvicorn app.main:app --reload  # http://127.0.0.1:8000
```

另开终端：

```bash
curl -s http://127.0.0.1:8000/healthz
curl -s -X POST http://127.0.0.1:8000/api/analyze \
  -H 'Content-Type: application/json' \
  --data @examples/diamond_story.json
```

## Docker Compose

只有 **api** 长驻；宿主映射端口由 `API_PORT` 决定（默认 8000）：

```bash
# 启动长驻 API（后台）
API_PORT=8080 docker compose up -d api

# 一次性校验服务：跑全部 pytest + 对 api 做 HTTP 冒烟，完成即退出
docker compose run --rm verify
# 或（按 profile 拉起）：
docker compose --profile verify up verify --build
```

`verify` 与 `api` 共用同一镜像；它通过 `depends_on: service_healthy`
等待 api 健康后再执行，`restart: "no"`，运行结束容器即退出。
