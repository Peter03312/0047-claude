#!/usr/bin/env python3
"""HTTP 冒烟：由 Compose 的 verify 服务对长驻 api 执行，一次运行即退出。

覆盖：
1. /healthz 存活；
2. 菱形汇合穿帮被抓出，反例路线可复述（start -> b -> meet，边序 [1,0]）；
3. 所有路径都持有时放行；
4. available_when 封闭了“丢秘密”的坏路后不再误报穿帮，且全封闭
   目标稳定归入不可达清单；
5. 悬空引用整单拒绝（422）。

用法：API_BASE_URL=http://api:8000 python scripts/smoke.py
"""

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")


def request(method: str, path: str, payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def check(name: str, condition: bool, detail: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {name}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        raise SystemExit(1)


DIAMOND = {
    "entry": "start",
    "scenes": [
        {
            "id": "start",
            "adds": ["secret"],
            "choices": [
                {"target": "a", "label": "走天台"},
                {"target": "b", "label": "走走廊"},
            ],
        },
        {"id": "a", "choices": [{"target": "meet"}]},
        {"id": "b", "removes": ["secret"], "choices": [{"target": "meet"}]},
        {"id": "meet", "requires": ["secret"]},
    ],
}

GOOD_GRAPH = {
    "entry": "start",
    "scenes": [
        {"id": "start", "adds": ["secret"], "choices": [{"target": "a"}]},
        {"id": "a", "requires": ["secret"], "choices": [{"target": "b"}]},
        {"id": "b", "requires": ["secret"]},
    ],
}

# 走廊支会丢秘密，但通往汇合点的选择只有持有秘密时才出现：
# 坏路实际不通，既不得误报穿帮；两条入边全封闭时 meet 必须不可达。
CONDITIONAL = {
    "entry": "start",
    "scenes": [
        {
            "id": "start",
            "adds": ["secret"],
            "choices": [
                {"target": "a", "label": "走天台"},
                {"target": "b", "label": "走走廊"},
            ],
        },
        {
            "id": "a",
            "choices": [{"target": "meet", "available_when": ["secret"]}],
        },
        {
            "id": "b",
            "removes": ["secret"],
            "choices": [{"target": "meet", "available_when": ["secret"]}],
        },
        {"id": "meet", "requires": ["secret"]},
    ],
}


def main() -> None:
    status, body = request("GET", "/healthz")
    check("healthz 返回 200", status == 200, str(status))
    check("healthz ok=true", body.get("ok") is True, str(body))

    status, body = request("POST", "/api/analyze", DIAMOND)
    check("菱形穿帮返回 200", status == 200, str(status))
    check("报告判定 violated", body.get("violated") is True, str(body))
    violation = body["violations"][0]
    check(
        "反例定位到 meet/secret",
        violation["scene"] == "meet" and violation["fact"] == "secret",
        str(violation),
    )
    route = [hop["scene"] for hop in violation["counterexample"]["route"]]
    check(
        "反例路线 start -> b -> meet",
        route == ["start", "b", "meet"],
        str(route),
    )
    check(
        "反例边序 [1, 0]",
        violation["counterexample"]["edge_indices"] == [1, 0],
        str(violation["counterexample"]["edge_indices"]),
    )

    status, body = request("POST", "/api/analyze", GOOD_GRAPH)
    check("合法图返回 200", status == 200, str(status))
    check("合法图无穿帮", body.get("violated") is False, str(body))

    status, body = request("POST", "/api/analyze", CONDITIONAL)
    check("条件图返回 200", status == 200, str(status))
    check(
        "封闭坏路后无误报",
        body.get("violated") is False and body.get("violations") == [],
        str(body),
    )
    check(
        "天台支仍可汇合",
        body.get("unreachable_scenes") == [],
        str(body.get("unreachable_scenes")),
    )

    sealed = json.loads(json.dumps(CONDITIONAL))
    sealed["scenes"][1]["choices"][0]["available_when"] = ["never"]
    status, body = request("POST", "/api/analyze", sealed)
    check("全封闭图返回 200", status == 200, str(status))
    check(
        "全封闭目标归入不可达且无违规",
        body.get("unreachable_scenes") == ["meet"]
        and body.get("violated") is False
        and body.get("violations") == [],
        str(body),
    )

    bad = json.loads(json.dumps(DIAMOND))
    bad["scenes"][0]["choices"][1]["target"] = "ghost"
    status, body = request("POST", "/api/analyze", bad)
    check("悬空引用返回 422", status == 422, str(status))
    codes = [issue["code"] for issue in body["issues"]]
    check("422 issue 为 dangling_edge", "dangling_edge" in codes, str(codes))

    print(f"\n冒烟全部通过（{BASE}）。")


if __name__ == "__main__":
    main()
