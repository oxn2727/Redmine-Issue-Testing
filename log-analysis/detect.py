# -*- coding: utf-8 -*-
"""检测层：对「请求记录」跑 6 条规则，命中即输出一条待确认问题。

规则设计上有一条关键取舍 —— **不是所有红色状态码都算缺陷**：

    5xx  服务端错误           → 一定是问题，High
    异常堆栈（FATAL/异常类）   → 一定是问题，High（哪怕状态码是 400）
    请求未完成（没 Completed）  → 一定是问题，High（进程被杀/超时）
    4xx  客户端/权限/校验拒绝  → **默认只统计，不报缺陷**
    慢请求 / 查询数过多        → 有优化价值，Medium

为什么 4xx 要压住：本项目被测对象是 Redmine，做越权测试时 403 是**预期结果**，
查不存在的 id 时 404 也是**预期结果**，创建时缺字段的 422 同样是预期。
如果把这些全报成缺陷，一份正常日志能刷出几十条假问题 —— 检测工具一旦满屏误报，
就没人看了。所以默认降级为 Info 只做分布统计，需要严格模式时用 --strict-4xx 提上来。

6 条规则：
    1. status_5xx     5xx 服务端错误
    2. exception      请求内出现 FATAL 级或异常类名（带调用栈）
    3. incomplete     Started 了但没有 Completed（请求被中断）
    4. status_4xx     4xx（默认 Info，--strict-4xx 时升为 Medium）
    5. slow           单请求耗时超阈值（默认 500ms）
    6. many_queries   单请求 SQL 条数超阈值（默认 40 条，N+1 嫌疑）
"""
import re
import statistics

# 默认阈值。数字不是拍脑袋：本机实测正常请求 200 OK 在 20~200ms、10~37 条 SQL，
# 所以 500ms / 40 条 SQL 是"明显高于正常水位"的位置。可用命令行参数覆盖。
DEFAULT_SLOW_MS = 500.0
DEFAULT_MAX_QUERIES = 40

SEVERITY_ORDER = {"High": 0, "Medium": 1, "Low": 2, "Info": 3}

RULE_TITLES = {
    "status_5xx": "服务端错误（5xx）",
    "exception": "服务端异常（带调用栈）",
    "incomplete": "请求未完成（无 Completed 行）",
    "status_4xx": "客户端错误（4xx）",
    "slow": "响应过慢",
    "many_queries": "单请求 SQL 条数过多（N+1 嫌疑）",
}

# 在堆栈里找「真实起因行」用的词：JSON::ParserError / NoMethodError / TimeoutError 这类。
# 外层异常通常是框架包的一层（ActionDispatch::Http::Parameters::ParseError），
# 真正原因在 Causes: 后面那行。
_RE_ERR_WORD = re.compile(r"\b[A-Z]\w*(?:::\w+)*(Error|Exception|NotFound|Failed)\b")


def _hit(rule, severity, detail):
    """构造一条规则命中结果。内部函数，统一 4 元组格式。

    Returns:
        tuple[str, str, str]: (规则名, 严重度, 人话说明)
    """
    return (rule, severity, detail)


def rule_status_5xx(rec, cfg):
    """规则 1 · 服务端错误：状态码 5xx。

    5xx 表示 Redmine 自己出错（异常没被捕获、依赖不可用、数据库连不上）。
    这类请求无论业务预期如何都是问题，直接 High。

    Args:
        rec (dict): 一条请求记录。
        cfg (dict): 阈值配置（本规则不用，保持签名统一）。

    Returns:
        list[tuple]: 空列表或一条命中。
    """
    if rec["status"] is not None and 500 <= rec["status"] < 600:
        return [_hit("status_5xx", "High",
                     f'{rec["status"]} {rec["status_text"]} —— {rec["method"]} {rec["path"]}')]
    return []


def rule_exception(rec, cfg):
    """规则 2 · 服务端异常：请求里出现 FATAL/ERROR 行，或抽到了异常类名。

    为什么这条不能只看状态码：实测中 Redmine 对「非法 JSON」返回的是 **400**，
    但同时打了 `F FATAL -- :` 和完整调用栈。状态码看着像客户端问题，
    实际上服务端代码确实抛了异常 —— 只看状态码会漏掉。

    Args:
        rec (dict): 一条请求记录。
        cfg (dict): 阈值配置（本规则不用）。

    Returns:
        list[tuple]: 空列表或一条命中（detail 里带异常类名和栈顶 2 行）。
    """
    if not rec["errors"] and rec["level"] not in ("ERROR", "FATAL"):
        return []
    kind = rec["error_kind"] or rec["level"]
    # 起因：跳过 "Causes:" 这类分隔行，找第一条带 Error/Exception 的行。
    # 真实标签形如 "JSON::ParserError (unexpected token at '{bad json')"，
    # 比外层那个 Http::Parameters::ParseError 具体得多，值得单独提出来。
    cause = ""
    for e in rec["errors"][1:]:
        if e.startswith("Causes") or not _RE_ERR_WORD.search(e):
            continue
        cause = e[:140]
        break
    detail = f"{kind}，起因 {cause}" if cause else kind
    if rec["status"] is not None and rec["status"] < 500:
        detail += f"（状态码 {rec['status']}，但服务端抛了异常）"
    return [_hit("exception", "High", detail)]


def rule_incomplete(rec, cfg):
    """规则 3 · 请求未完成：有 Started / Processing，但没有 Completed 行。

    常见原因：进程被 kill、请求超时、容器重启、连接被客户端掐断。
    这是「日志里最容易漏看」的一类问题 —— 没有 Completed 就没有状态码，
    靠状态码统计的工具会直接把它跳过。

    注意：日志文件末尾那条大概率是被截断（不是故障），所以跳过判断，
    交给报告里单独说明。

    Args:
        rec (dict): 一条请求记录。
        cfg (dict): 阈值配置（本规则不用）。

    Returns:
        list[tuple]: 空列表或一条命中。
    """
    if rec["completed"] or rec.get("truncated"):
        return []
    return [_hit("incomplete", "High",
                 f'{rec["method"]} {rec["path"]} 停在 L{rec["last_lineno"]}，没有 Completed 行')]


def rule_status_4xx(rec, cfg):
    """规则 4 · 客户端错误：状态码 4xx（默认 Info，严格模式升 Medium）。

    默认压成 Info 的原因见模块顶部：越权测试的 403、查不存在的 404、参数校验的 422
    都是**预期行为**。但它们的分布仍然有价值（能看出接口被拒的比例），
    所以照样记录，只是不升级成缺陷。

    Args:
        rec (dict): 一条请求记录。
        cfg (dict): 需含 "strict_4xx"（bool）。

    Returns:
        list[tuple]: 空列表或一条命中。
    """
    if rec["status"] is None or not (400 <= rec["status"] < 500):
        return []
    sev = "Medium" if cfg.get("strict_4xx") else "Info"
    extra = f'，被 :{rec["halted_by"]} 拦截' if rec["halted_by"] else ""
    return [_hit("status_4xx", sev,
                 f'{rec["status"]} {rec["status_text"]} —— {rec["method"]} {rec["path"]}{extra}')]


def rule_slow(rec, cfg):
    """规则 5 · 响应过慢：单请求耗时超过阈值。

    Args:
        rec (dict): 一条请求记录。
        cfg (dict): 需含 "slow_ms"（float）。

    Returns:
        list[tuple]: 空列表或一条命中（detail 里拆开总耗时与 SQL 耗时占比）。
    """
    limit = cfg.get("slow_ms", DEFAULT_SLOW_MS)
    if rec["duration_ms"] is None or rec["duration_ms"] <= limit:
        return []
    ar = rec["ar_ms"]
    share = ""
    if ar:
        ratio = ar / rec["duration_ms"] * 100
        share = f"，其中 SQL {ar:g}ms 占 {ratio:.0f}%"
    return [_hit("slow", "Medium",
                 f'{rec["duration_ms"]:g}ms > {limit:g}ms{share} —— {rec["method"]} {rec["path"]}')]


def rule_many_queries(rec, cfg):
    """规则 6 · SQL 条数过多：暗示 N+1 查询。

    典型症状：列表接口按条数线性翻 SQL —— 取 20 条 Issue 跑出 33 条 SQL。
    这类问题功能测试完全测不出来（结果是对的），只有日志能看见。

    Args:
        rec (dict): 一条请求记录。
        cfg (dict): 需含 "max_queries"（int）。

    Returns:
        list[tuple]: 空列表或一条命中。
    """
    limit = cfg.get("max_queries", DEFAULT_MAX_QUERIES)
    if rec["queries"] is None or rec["queries"] <= limit:
        return []
    return [_hit("many_queries", "Medium",
                 f'{rec["queries"]} 条 SQL > {limit} —— {rec["method"]} {rec["path"]}')]


RULES = (rule_status_5xx, rule_exception, rule_incomplete,
         rule_status_4xx, rule_slow, rule_many_queries)


def detect(records, cfg=None):
    """主流程：对每条请求跑完 6 条规则，返回按严重度排序的待确认问题列表。

    Args:
        records (list[dict]): parse_rails.merge() 的输出。
        cfg (dict | None): 阈值配置，可含 slow_ms / max_queries / strict_4xx；
            不传则用默认值。

    Returns:
        list[dict]: 每条命中一个问题，字段：
            severity (str)  High / Medium / Low / Info
            rule     (str)  规则名，如 "status_5xx"
            title    (str)  规则中文名
            detail   (str)  人话说明
            record   (dict) 对应的请求记录（写缺陷单时要用）
        排序：先按严重度（High 在前），同级按时间先后（lineno 升序）。
    """
    cfg = cfg or {}
    findings = []
    for rec in records:
        for rule in RULES:
            for name, severity, detail in rule(rec, cfg):
                findings.append({
                    "severity": severity,
                    "rule": name,
                    "title": RULE_TITLES.get(name, name),
                    "detail": detail,
                    "record": rec,
                })
    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9), f["record"]["lineno"]))

    # 同一个请求已经因为更严重的原因被报出来了，就不再重复列它的 4xx 信息条。
    # 例：400 + FATAL 堆栈的请求，报「服务端异常」就够，不必再报一条「客户端错误 400」。
    real_linenos = {f["record"]["lineno"] for f in findings
                    if f["severity"] in ("High", "Medium")}
    findings = [f for f in findings
                if f["severity"] in ("High", "Medium") or f["record"]["lineno"] not in real_linenos]
    return findings


def stat_records(records):
    """算一批请求的统计口径，供报告抬头和各附表使用。

    Args:
        records (list[dict]): parse_rails.merge() 的输出。

    Returns:
        dict: 含以下键
            requests (int)        请求总数
            with_status (int)     有状态码的请求数
            status_count (dict)   {状态码: 次数}，按状态码升序
            slowest (list[dict])  耗时 top5 的请求记录（降序）
            busiest (list[dict])  按 SQL 条数 top5（降序）
            p50_ms / p95_ms / avg_ms (float | None)  响应时间分位
            by_controller (list)  [(controller, 次数, 平均耗时)] 按次数降序
    """
    with_status = [r for r in records if r["status"] is not None]
    durations = sorted([r["duration_ms"] for r in with_status if r["duration_ms"] is not None])

    def pct(p):
        if not durations:
            return None
        idx = min(int(len(durations) * p), len(durations) - 1)
        return durations[idx]

    status_count = {}
    for r in with_status:
        status_count[r["status"]] = status_count.get(r["status"], 0) + 1

    ctrl = {}
    for r in records:
        key = r["controller"] or "(未识别)"
        n, total = ctrl.get(key, (0, 0.0))
        ctrl[key] = (n + 1, total + (r["duration_ms"] or 0.0))

    return {
        "requests": len(records),
        "with_status": len(with_status),
        "status_count": dict(sorted(status_count.items())),
        "slowest": sorted(with_status, key=lambda r: r["duration_ms"] or 0, reverse=True)[:5],
        "busiest": sorted([r for r in with_status if r["queries"] is not None],
                          key=lambda r: r["queries"], reverse=True)[:5],
        "p50_ms": pct(0.50),
        "p95_ms": pct(0.95),
        "avg_ms": round(statistics.mean(durations), 1) if durations else None,
        "by_controller": sorted([(k, v[0], round(v[1] / v[0], 1)) for k, v in ctrl.items()],
                                key=lambda x: -x[1]),
    }
