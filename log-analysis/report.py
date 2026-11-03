# -*- coding: utf-8 -*-
"""输出层：控制台概览 + Markdown 缺陷单 + Markdown 汇总报告。

为什么不用 HTML 报告：这个工具的价值在「快速定位到哪几条请求有问题」，
不是在展示。控制台看完能直接进 Redmine 提单就够；缺陷单是 Markdown，
可以直接贴进 Redmine 的 Issue 描述框（Redmine 原生支持 Markdown 语法）。
"""
import datetime
import os

SEVERITY_MARK = {"High": "[高]", "Medium": "[中]", "Low": "[低]", "Info": "[信息]"}

# 每条规则命中后建议怎么查 —— 这部分是「经验」，工具本身看不出来，写死成提示
SUGGEST = {
    "status_5xx": "看同 request_id 的完整堆栈（缺陷单「日志原文」段），确认是代码异常还是依赖不可用"
                  "（数据库/文件系统）；对照 Redmine 版本是否有已知 issue。",
    "exception": "堆栈第一帧是出事位置；`Causes:` 段是真实原因。"
                 "如果是 `ActiveRecord::` 开头，优先查数据库连接与慢查询。",
    "incomplete": "没有 Completed 说明请求没走完：查容器是否重启过（docker ps 的 Up 时间）、"
                  "Puma 是否被 OOM 杀掉（dmesg / docker inspect 的 OOMKilled）。",
    "status_4xx": "4xx 多为预期行为（越权 403 / 不存在 404 / 校验失败 422）。"
                  "若这里出现**非测试预期的** 4xx，再看 halted_by 字段是被哪个过滤器拦的。",
    "slow": "先看 SQL 耗时占比：占比高 → 查索引与 N+1；占比低 → 查视图渲染或 GC。",
    "many_queries": "典型 N+1：列表接口按返回条数线性翻 SQL。"
                    "对同一 path 改 limit 值再压一次，SQL 条数跟着涨就是 N+1。",
}


def fmt_ms(v):
    """毫秒数 → 去掉多余小数位的字符串（80.0 → "80"，0.5 → "0.5"）。None → "?"。"""
    if v is None:
        return "?"
    return f"{v:g}"


def fmt_ts(epoch):
    """Unix 秒 → "2026-11-03 13:59:50 UTC"。epoch 为空时返回 "?"。

    Rails 日志的时间是 UTC，这里统一标 UTC 避免和本地时间（+8）混淆。
    """
    if epoch is None:
        return "?"
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def print_summary(records, stats, findings, title="Redmine 日志分析"):
    """把概览、状态码分布、问题清单、最慢请求打印到控制台。

    Args:
        records (list[dict]): 请求记录。
        stats (dict): detect.stat_records() 的结果。
        findings (list[dict]): detect.detect() 的结果。
        title (str): 报告标题，一般传日志文件名。

    Returns:
        None: 只打印，不返回数据。
    """
    line = "=" * 72
    print(line)
    print(f"  {title}")
    print(line)
    print(f"  请求总数 {stats['requests']}   有状态码 {stats['with_status']}")

    # 状态码分布：一行一个码，附占比，5xx 单独标出来
    if stats["status_count"]:
        parts = []
        for code, n in stats["status_count"].items():
            parts.append(f"{code}×{n}")
        print(f"  状态码  " + "   ".join(parts))

    if stats["avg_ms"] is not None:
        print(f"  响应    P50 {stats['p50_ms']:g}ms   P95 {stats['p95_ms']:g}ms   平均 {stats['avg_ms']:g}ms")

    # 问题清单
    real = [f for f in findings if f["severity"] in ("High", "Medium")]
    info = [f for f in findings if f["severity"] not in ("High", "Medium")]
    print()
    print(f"  检出问题 {len(real)} 条" + (f"（另有 {len(info)} 条信息级，见 --all）" if info else ""))
    print()

    for f in real:
        rec = f["record"]
        print(f"  {SEVERITY_MARK.get(f['severity'], '')} {f['title']}")
        print(f"      L{rec['lineno']}  {rec['raw']}")
        print(f"      {f['detail']}")
        print()

    # 最慢 3 条：即使没超阈值，也让人知道水位在哪
    if stats["slowest"]:
        print("  最慢请求 top3")
        for r in stats["slowest"][:3]:
            ms = f"{r['duration_ms']:g}ms" if r["duration_ms"] is not None else "?"
            print(f"      {ms:>8}  {r['raw'][:88]}")
        print()

    if info:
        print(f"  信息级（{len(info)} 条，默认不算问题）")
        for f in info[:10]:
            print(f"      {f['detail'][:96]}")
        if len(info) > 10:
            print(f"      ... 还有 {len(info) - 10} 条")
        print()


def write_bug_files(findings, out_dir, only_severities=("High", "Medium")):
    """把每条问题写成一张 Markdown 缺陷单，可直接贴进 Redmine。

    Args:
        findings (list[dict]): detect.detect() 的结果。
        out_dir (str): 输出目录，不存在会自动创建。
        only_severities (tuple[str]): 只给这些严重度出单，默认 High + Medium。

    Returns:
        list[str]: 生成的文件路径列表（按传入顺序）。
    """
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    picked = [f for f in findings if f["severity"] in only_severities]

    for i, f in enumerate(picked, start=1):
        rec = f["record"]
        name = f"bug-{i:02d}-{f['rule']}-L{rec['lineno']}.md"
        path = os.path.join(out_dir, name)

        dur = f'{rec["duration_ms"]:g}ms' if rec["duration_ms"] is not None else "?"
        sql = (f'{rec["ar_ms"]:g}ms / {rec["queries"]} 条'
               if rec["queries"] is not None else "?")

        body = [
            f"# [日志] {f['title']} —— {rec['method']} {rec['path']}",
            "",
            "| 项 | 内容 |",
            "|---|---|",
            f"| 严重程度 | **{f['severity']}** |",
            f"| 触发规则 | `{f['rule']}` |",
            f"| 请求 | `{rec['method']} {rec['path']}` |",
            f"| 状态码 | {rec['status'] if rec['status'] is not None else '无 Completed 行'} {rec['status_text']} |",
            f"| 控制器 | {rec['controller'] or '?'} |",
            f"| 操作人 | {rec['user'] or '?'} |",
            f"| 时间 | {fmt_ts(rec['epoch'])} |",
            f"| 耗时 | {dur}（SQL {sql}） |",
            f"| 请求参数 | `{rec['params'] or '-'}` |",
            f"| 拦截过滤器 | {rec['halted_by'] or '-'} |",
            f"| 日志行 | L{rec['lineno']} ~ L{rec['last_lineno']} |",
            f"| request_id | `{rec['request_id']}` |",
            "",
            "## 现象",
            "",
            f["detail"],
            "",
            "## 日志原文",
            "",
            "```",
        ]
        # 合并摘要在前，异常堆栈在后 —— 看单子的人先看结论再看细节
        body.append(rec["raw"])
        if rec["errors"]:
            body.append("")
            body.extend(rec["errors"][:15])
            if len(rec["errors"]) > 15:
                body.append(f"... 另有 {len(rec['errors']) - 15} 行，按 request_id 回原日志查")
        body += [
            "```",
            "",
            "## 建议排查",
            "",
            SUGGEST.get(f["rule"], "按 request_id 回原始日志查看完整上下文。"),
            "",
        ]

        with open(path, "w", encoding="utf-8") as fp:
            fp.write("\n".join(body))
        paths.append(path)
    return paths


def write_report_md(records, stats, findings, path, title="Redmine 日志分析报告"):
    """写一份 Markdown 汇总报告（概览 + 分布 + 问题表 + 慢请求表）。

    Args:
        records (list[dict]): 请求记录。
        stats (dict): detect.stat_records() 的结果。
        findings (list[dict]): detect.detect() 的结果。
        path (str): 输出文件路径。
        title (str): 报告标题。

    Returns:
        str: 实际写入的路径。
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    real = [f for f in findings if f["severity"] in ("High", "Medium")]

    lines = [f"# {title}", "",
             f"> 请求 {stats['requests']} 个 ｜ 检出问题 {len(real)} 条 ｜ "
             f"P50 {fmt_ms(stats['p50_ms'])}ms ｜ P95 {fmt_ms(stats['p95_ms'])}ms", "",
             "## 一、状态码分布", "", "| 状态码 | 次数 | 说明 |", "|---|---|---|"]

    note = {200: "正常", 201: "创建成功", 204: "成功无内容",
            400: "请求格式错", 401: "未认证", 403: "无权限",
            404: "资源不存在", 422: "参数校验失败", 500: "服务端异常"}
    for code, n in stats["status_count"].items():
        lines.append(f"| {code} | {n} | {note.get(code, '-')} |")

    lines += ["", "## 二、问题清单", "",
              "| # | 严重度 | 规则 | 请求 | 行号 | 说明 |",
              "|---|---|---|---|---|---|"]
    for i, f in enumerate(real, start=1):
        rec = f["record"]
        # detail 里已经带了 "—— METHOD /path"，表格已有请求列，这里截掉避免重复
        brief = f["detail"].split(" —— ")[0][:90]
        lines.append(f"| {i} | {f['severity']} | {f['title']} | "
                     f"`{rec['method']} {rec['path']}` | L{rec['lineno']} | {brief} |")
    if not real:
        lines.append("| - | - | - | - | - | 未检出 High/Medium 问题 |")

    lines += ["", "## 三、最慢请求 top5", "",
              "| 耗时 | SQL | 请求 | 控制器 |", "|---|---|---|---|"]
    for r in stats["slowest"]:
        ms = f"{r['duration_ms']:g}ms" if r["duration_ms"] is not None else "?"
        sql = f"{r['queries']}q" if r["queries"] is not None else "-"
        lines.append(f"| {ms} | {sql} | `{r['method']} {r['path']}` | {r['controller'] or '-'} |")

    lines += ["", "## 四、SQL 条数 top5（N+1 嫌疑）", "",
              "| SQL 条数 | 请求 | 状态码 | 耗时 |", "|---|---|---|---|"]
    for r in stats["busiest"]:
        ms = f"{r['duration_ms']:g}ms" if r["duration_ms"] is not None else "?"
        lines.append(f"| {r['queries']} | `{r['method']} {r['path']}` | {r['status']} | {ms} |")

    lines += ["", "## 五、按控制器聚合", "", "| 控制器 | 请求数 | 平均耗时 |", "|---|---|---|"]
    for ctrl, n, avg in stats["by_controller"]:
        lines.append(f"| {ctrl} | {n} | {avg}ms |")

    lines.append("")
    with open(path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines))
    return path
