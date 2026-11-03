# -*- coding: utf-8 -*-
"""解析层：把 Rails 的多行日志，还原成「一个 HTTP 请求 = 一条记录」。

这是整个项目最核心的一层，因为 Redmine 日志和普通 nginx 日志有本质区别：

    nginx          1 行 = 1 个请求，直接读就行
    Rails/Redmine  1 个请求 = 5~20 行，靠 [request_id] 串起来

一个正常请求长这样（5 行，uuid 相同）：

    I, [2026-11-03T13:59:50.134426 #1]  INFO -- : [321094fe-...] Started GET "/issues/293.json" for 172.18.0.1 ...
    I, [...] [321094fe-...] Processing by IssuesController#show as JSON
    I, [...] [321094fe-...]   Parameters: {"id" => "293"}
    I, [...] [321094fe-...]   Current user: admin (id=1)
    I, [...] [321094fe-...] Completed 200 OK in 80ms (Views: 9.9ms | ActiveRecord: 52.8ms (15 queries, 0 cached) | GC: 1.2ms)

出异常时会再多一段堆栈，**注意堆栈行没有 `I, [时间 #PID] INFO -- :` 前缀**，
只剩 `[uuid] 正文`：

    F, [...] FATAL -- : [bd4cca84-...]
    [bd4cca84-...] ActionDispatch::Http::Parameters::ParseError (Error occurred while parsing request parameters):
    [bd4cca84-...] Causes:
    [bd4cca84-...] JSON::ParserError (unexpected token at '{bad json')
    [bd4cca84-...] app/controllers/application_controller.rb:737:in 'ApplicationController#api_request?'

所以本层要认两种行：
    标准行  ^X, [时间 #PID]  级别 -- : [uuid] 正文
    堆栈行  ^[uuid] 正文                        ← 没有级别、没有时间戳

处理完输出「请求记录」dict，后面所有检测规则只面对这一种结构，
不需要再关心日志格式 —— 这是分层的意义。
"""
import datetime
import re

# ---------------------------------------------------------------- 行级正则

# 标准行：`I, [2026-11-03T13:59:50.134426 #1]  INFO -- : [uuid] 正文`
RE_ENTRY = re.compile(
    r"^(?P<flag>[A-Z]),\s+\[(?P<ts>[^\]]+?)\s+#(?P<pid>\d+)\]\s+"
    r"(?P<level>[A-Z]+)\s+--\s+:\s+"
    r"(?:\[(?P<rid>[0-9a-fA-F-]{8,})\]\s?)?(?P<body>.*)$"
)

# 堆栈续行：`[uuid] 正文`（Rails 抛异常后的调用栈，没有时间戳和级别）
RE_STACK = re.compile(r"^\[(?P<rid>[0-9a-fA-F-]{8,})\](?P<body>.*)$")

# ---------------------------------------------------------------- 正文正则

RE_STARTED = re.compile(r'^Started (?P<method>[A-Z]+) "(?P<path>[^"]*)"')
RE_PROCESSING = re.compile(r"^Processing by (?P<controller>[\w:]+#\w+) as (?P<fmt>\S+)")
RE_PARAMS = re.compile(r"^\s+Parameters: (?P<params>.*)$")
RE_USER = re.compile(r"^\s+Current user: (?P<user>[\w.\-@]+)(?: \(id=(?P<uid>\d+)\))?")
RE_HALTED = re.compile(r"^Filter chain halted as :(?P<filter>[\w!?]+)")
RE_COMPLETED = re.compile(r"^Completed (?P<code>\d{3})(?: (?P<text>.*))?$")
# Completed 后面的耗时：`OK in 80ms (...)` → text=OK, ms=80
RE_IN_MS = re.compile(r"^(?P<text>.*?)\s+in\s+(?P<ms>[\d.]+)ms")
RE_VIEWS = re.compile(r"Views: ([\d.]+)ms")
RE_AR = re.compile(r"ActiveRecord: ([\d.]+)ms")
RE_QUERIES = re.compile(r"\((\d+) queries")

# 日志级别排序，用于「一个请求内取最高级别」
LEVEL_RANK = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3, "FATAL": 4}
# 单字母 flag 与级别名的对应（Rails 第一段只给一个字母）
FLAG_TO_LEVEL = {"D": "DEBUG", "I": "INFO", "W": "WARN", "E": "ERROR", "F": "FATAL"}


def is_rails_log(lines):
    """判断一份日志是不是 Rails/Redmine 格式。

    抽样前 200 行算命中率，超过 5% 就认为是 Rails 日志。
    为什么要判断：这个工具明确定位 Redmine，但如果有人拿 nginx 日志喂进来，
    应该直接告诉他不支持，而不是默默输出 0 条结果让他以为"没问题"。

    Args:
        lines (list[tuple[int, str]]): collect 层输出的 (行号, 原文)。

    Returns:
        bool: True = 像 Rails 日志；False = 不像。
    """
    sample = lines[:200]
    if not sample:
        return False
    hit = sum(1 for _, line in sample if RE_ENTRY.match(line))
    return hit / len(sample) > 0.05


def to_epoch(ts):
    """把 Rails 的时间戳转成 Unix 秒（UTC）。

    Rails 日志的时间是**UTC**（容器默认时区 UTC），和本地时间差 8 小时。
    这里显式按 UTC 解析，否则做「时间窗统计」时会整体偏移 8 小时。

    Args:
        ts (str): 如 "2026-11-03T13:59:50.134426"。

    Returns:
        float | None: Unix 秒；解析失败返回 None（不会抛异常，避免一条坏数据干掉整次分析）。
    """
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.datetime.strptime(ts.strip(), fmt)
            return dt.replace(tzinfo=datetime.timezone.utc).timestamp()
        except ValueError:
            continue
    return None


def _new_group(rid, lineno, ts, level):
    """建一个空的请求记录（内部用，字段在这里一次列全）。"""
    return {
        "request_id": rid,
        "lineno": lineno,                 # 这个请求的第一行在原始文件里的行号
        "last_lineno": lineno,
        "timestamp": ts,
        "epoch": to_epoch(ts) if ts else None,
        "method": None,
        "path": None,
        "controller": None,
        "format": None,
        "status": None,
        "status_text": "",
        "duration_ms": None,
        "view_ms": None,
        "ar_ms": None,
        "queries": None,
        "user": None,
        "params": None,
        "halted_by": None,
        "level": level or "INFO",
        "errors": [],                     # FATAL/异常堆栈的正文，按出现顺序
        "completed": False,
        "line_count": 0,
    }


def _apply_body(g, body):
    """解析一行正文，把抽到的字段写进记录 g。内部函数，原地修改。"""
    g["line_count"] += 1

    if m := RE_STARTED.match(body):
        g["method"] = m.group("method")
        g["path"] = m.group("path")
    elif m := RE_PROCESSING.match(body):
        g["controller"] = m.group("controller")
        g["format"] = m.group("fmt")
    elif m := RE_COMPLETED.match(body):
        g["completed"] = True
        g["status"] = int(m.group("code"))
        rest = (m.group("text") or "").strip()
        if mm := RE_IN_MS.match(rest):
            g["status_text"] = mm.group("text").strip()
            g["duration_ms"] = float(mm.group("ms"))
        else:
            g["status_text"] = rest
        if v := RE_VIEWS.search(rest):
            g["view_ms"] = float(v.group(1))
        if a := RE_AR.search(rest):
            g["ar_ms"] = float(a.group(1))
        if q := RE_QUERIES.search(rest):
            g["queries"] = int(q.group(1))
    elif m := RE_PARAMS.match(body):
        g["params"] = m.group("params")[:200]
    elif m := RE_USER.match(body):
        g["user"] = m.group("user")
    elif m := RE_HALTED.match(body):
        g["halted_by"] = m.group("filter")


def merge(lines):
    """把逐行日志合并成「请求记录」列表 —— 本模块的主函数。

    做法：按 [request_id] 分组，同一组的所有行累积到一条记录里，
    最后按**首次出现顺序**输出（即日志的时间顺序）。

    Args:
        lines (list[tuple[int, str]]): collect 层输出。

    Returns:
        tuple[list[dict], int]:
            [0] 请求记录列表，字段见 _new_group()，另加三个汇总字段
                raw / truncated / error_kind（由 _finalize 补）；
            [1] 被丢弃的行数。丢弃的是没有 request_id 的行 —— 启动期的
                Gemfile 警告、静态资源编译（`Writing xxx.woff2`）、ActiveJob 等，
                它们不属于任何请求，留着只会污染模板统计。
    """
    groups = {}          # rid -> 记录
    order = []           # rid 的首次出现顺序
    skipped = 0

    for lineno, line in lines:
        m = RE_ENTRY.match(line)
        if m:
            rid = m.group("rid")
            level = m.group("level") or FLAG_TO_LEVEL.get(m.group("flag"), "INFO")
            body = m.group("body") or ""

            if not rid:
                # 有级别有时间但没有 uuid：启动期日志 / ActiveJob，不属于任何请求
                skipped += 1
                continue

            if rid not in groups:
                groups[rid] = _new_group(rid, lineno, m.group("ts"), level)
                order.append(rid)

            g = groups[rid]
            g["last_lineno"] = lineno
            _apply_body(g, body)

            # 同一请求里出现更高级别的行（比如 INFO 中间夹一个 FATAL），取最高
            if LEVEL_RANK.get(level, 1) > LEVEL_RANK.get(g["level"], 1):
                g["level"] = level

            # FATAL 行的正文通常为空，真正内容在后面的堆栈行里，先记一句占位
            if level in ("ERROR", "FATAL") and body.strip():
                g["errors"].append(body.strip())
            continue

        s = RE_STACK.match(line)
        if s and s.group("rid") in groups:
            text = (s.group("body") or "").strip()
            if text:
                g = groups[s.group("rid")]
                g["last_lineno"] = lineno
                if text not in g["errors"]:
                    g["errors"].append(text)
            continue

        # 两种都不匹配：静态资源编译行、"=> Booting Puma" 这类纯文本
        skipped += 1

    records = [_finalize(groups[rid]) for rid in order]
    # 只有一条记录时不存在"被截断"的歧义；最后一条没 Completed 就标记为可能被截断
    if records and not records[-1]["completed"]:
        records[-1]["truncated"] = True
    return records, skipped


def _finalize(g):
    """收尾：补 raw 摘要 / error_kind / truncated，让记录可以直接打印和写缺陷单。

    Args:
        g (dict): 累积好的请求记录。

    Returns:
        dict: 同一个对象（原地加工），多出 3 个字段：
            raw        (str)  一行人类可读摘要，检测规则的兜底判断也用它
            error_kind (str)  异常类名，如 "JSON::ParserError"；没有则空串
            truncated  (bool) 是否是「日志末尾未完成」的那一条
    """
    parts = []
    parts.append(f'{g["method"] or "?"} {g["path"] or "?"}')
    if g["status"] is not None:
        parts.append(f'-> {g["status"]} {g["status_text"]}'.rstrip())
    else:
        parts.append("-> NO_COMPLETED")
    if g["duration_ms"] is not None:
        parts.append(f'in {g["duration_ms"]:g}ms')
    if g["queries"] is not None:
        parts.append(f'({g["queries"]}q)')
    if g["controller"]:
        parts.append(g["controller"])
    if g["user"]:
        parts.append(f'user={g["user"]}')
    if g["halted_by"]:
        parts.append(f'halted_by={g["halted_by"]}')

    # 异常类名：形如 "JSON::ParserError (unexpected token ...)" 取括号前那段
    g["error_kind"] = ""
    for e in g["errors"]:
        m = re.match(r"^([A-Z][\w:]*(?:Error|Exception|Invalid|NotFound|Timeout))\b", e)
        if m:
            g["error_kind"] = m.group(1)
            break
    if g["error_kind"]:
        parts.append(f"!! {g['error_kind']}")

    g["raw"] = "  ".join(parts)
    g["truncated"] = False
    return g
