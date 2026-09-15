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
- `available_when`（可选，写在某条 `choice` 上）：事实列表，给出该选择
  **出现的条件**。读者在出发场景完成“先 `removes` 后 `adds`”更新后，
  必须**全部持有**这些事实，这条选择才可走；缺省或 `[]` 表示无条件开放。
  条件不满足时这条边视为封闭——作者本意就是“读者还没掌握线索时看不到
  这个选项”，分析绝不能沿一条读者实际走不到的路线误报穿帮。

判定规则（关键）：

1. **只分析从入口沿“当时开放的选择”可达的场景**。分析在 DAG 内按读者
   真实持有的事实状态推进：出发场景更新后 `available_when` 条件全部
   成立的边才可走，事实集相同的等价状态合并。所有入边都因条件不满足
   而封闭的场景（及其无法另路抵达的下游）仅在报告中列为不可达，
   **不产生 `requires` 违规**；结构上与入口不连通的孤立场景同样只列出。
2. 某个 `requires` 事实，必须在**从入口到该场景的每一条可行前驱路径**
   上都成立。多条支线在此取事实**交集**——**禁止用各分支事实的并集
   放行**，并集正是“凭空知情”的来源；被条件封闭、读者实际走不到的
   伪路线同样不得进入交集。
3. 存在不成立的可行路径时，返回**最短反例**：
   - 只穿过当时可用的选择（封闭边不得出现在反例路线里）；
   - 先比路径长度（边数）；
   - 长度相同时，把路线上每条边在其 `choices` 中的下标组成序列，
     按字典序取最小（边序最小）的一条；
   - 反例是真实存在的一条读者路线，沿途事实逐场景真实更新，
     不是各分支拼出来的。
4. **整单拒绝**（HTTP 422，不出半截报告）：
   - 图中存在环（含自环，条件边仍参与环检测）；
   - 边指向不存在的场景（悬空引用，条件边不豁免）；
   - 同一场景对同一事实既 `adds` 又 `removes`；
   - 场景 id 重复；`entry` 指向不存在的场景；请求体不符合模型
     （例如 `available_when` 不是字符串列表，错误定位到具体场景/选择）。
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

#### 条件选择：`available_when`

把上面的“走廊”边改成只有仍知道秘密的读者才看得到的选项：

```json
{
  "id": "branch_b",
  "removes": ["secret"],
  "choices": [
    {"target": "meet", "available_when": ["secret"]}
  ]
}
```

走走廊的读者在 `branch_b` 更新后已经没有 `secret`，这条选择对他**不出现**，
即没有任何可行路线能沿这条边到达 `meet`：

- 不再报 `meet/secret` 穿帮（旧分析会把这条实际不通的路线当成反例）；
- 若 `meet` 的另一条入边（天台）也带着永不满足的条件，则 `meet` 进入
  `unreachable_scenes`，且不会产生任何 `requires` 违规；
- 若穿帮仍能经由某条**可行**路线发生（例如更长的另一条走廊），返回的
  仍是可行路线中最短、边序最小的反例，封闭捷径不会出现在路线里。

`available_when` 缺省或为 `[]` 时无条件开放，旧投稿的请求与响应完全不变。

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
| `app/models.py` | Pydantic 图模型（场景、边、`available_when` 条件、事实），输入顺序即边序 |
| `app/graph.py` | 结构校验（环/悬空/增删冲突，条件边不豁免）、结构可达性、拓扑序 |
| `app/propagation.py` | 真实事实状态推进 + 等价状态合并；可行路线取交集，禁止并集放行 |
| `app/counterexample.py` | 显式状态图 BFS：只穿当时可用边，最短 + 边序最小反例回溯 |
| `app/service.py` | 编排分析、条件可达性与可定位的稳定 JSON 报告 |
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
