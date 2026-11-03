# -*- coding: utf-8 -*-
"""Redmine 日志分析器 —— 命令行入口。

用法（在本目录下执行）：

    python analyze.py sample/redmine.log                    # 分析内置样本
    python analyze.py 日志路径/redmine.log                   # 分析指定文件
    python analyze.py --docker redmin_test-redmine-1        # 直接从容器取日志
    python analyze.py --docker redmin_test-redmine-1 --since 30m
    docker logs redmin_test-redmine-1 2>&1 | python analyze.py -    # 管道

常用参数：

    --slow 300           慢请求阈值（毫秒，默认 500）
    --queries 20         单请求 SQL 条数阈值（默认 40）
    --strict-4xx         把 4xx 从「信息级」升级为「问题」
    --all                控制台也打印信息级条目
    --no-bugs            只打印，不生成缺陷单文件
    --json out.json      把解析出的请求记录导出成 JSON

产出：
    reports/bug-NN-规则-L行号.md    每条问题一张缺陷单（可直接贴进 Redmine）
    reports/summary.md              汇总报告（状态码分布 / 问题表 / 慢请求 / SQL top）
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import collect                                            # noqa: E402
import parse_rails                                        # noqa: E402
import detect as detector                                 # noqa: E402
import report                                             # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    """解析命令行 → 采集 → 合并 → 检测 → 输出。

    Returns:
        int: 进程退出码。0 = 跑完（不代表没问题）；2 = 输入不是 Rails 日志。
    """
    ap = argparse.ArgumentParser(
        description="Redmine（Rails）日志分析：把多行日志还原成请求，按 6 条规则找问题")
    ap.add_argument("source", nargs="?", default=os.path.join(HERE, "sample", "redmine.log"),
                    help="日志文件路径，或 '-' 表示从标准输入读")
    ap.add_argument("--docker", metavar="容器名", default=None,
                    help="直接从 docker 容器取日志（此时 source 可省略）")
    ap.add_argument("--since", default=None, help="配合 --docker：只取这段时间之后，如 30m")
    ap.add_argument("--tail", type=int, default=None, help="配合 --docker：只取最后 N 行")
    ap.add_argument("--slow", type=float, default=detector.DEFAULT_SLOW_MS,
                    help=f"慢请求阈值毫秒（默认 {detector.DEFAULT_SLOW_MS:g}）")
    ap.add_argument("--queries", type=int, default=detector.DEFAULT_MAX_QUERIES,
                    help=f"单请求 SQL 条数阈值（默认 {detector.DEFAULT_MAX_QUERIES}）")
    ap.add_argument("--strict-4xx", action="store_true", help="把 4xx 升级为问题（Medium）")
    ap.add_argument("--all", action="store_true", help="控制台同时打印信息级条目")
    ap.add_argument("--no-bugs", action="store_true", help="不生成缺陷单文件")
    ap.add_argument("--json", metavar="路径", default=None, help="导出请求记录 JSON")
    ap.add_argument("--out", metavar="目录", default=os.path.join(HERE, "reports"),
                    help="缺陷单与汇总报告输出目录（默认 reports/）")
    args = ap.parse_args()

    # ---------- ① 采集 ----------
    try:
        if args.docker:
            lines = collect.read_docker(args.docker, since=args.since, tail=args.tail)
            title = f"docker logs {args.docker}"
        elif args.source == "-":
            lines = collect.read_stdin()
            title = "标准输入"
        else:
            if not os.path.exists(args.source):
                sys.exit(f"❌ 文件不存在：{args.source}")
            lines = collect.read_file(args.source)
            title = os.path.basename(args.source)
    except RuntimeError as e:
        sys.exit(f"❌ {e}")

    if not lines:
        sys.exit("❌ 日志为空，检查路径或容器名是否正确")

    # ---------- ② 判格式 ----------
    # 不做猜测：明确不是 Rails 格式就直接退出，避免输出「0 个问题」让人误以为日志干净
    if not parse_rails.is_rails_log(lines):
        sys.exit("❌ 这不像 Rails/Redmine 日志（找不到 `I, [时间 #PID] 级别 -- : [uuid]` 形态的行）。\n"
                 "   本工具只处理 Redmine 输出；nginx 等单行日志请用 ai-log-analyzer。")

    # ---------- ③ 合并成请求 ----------
    records, skipped = parse_rails.merge(lines)

    # ---------- ④ 检测 ----------
    cfg = {
        "slow_ms": args.slow,
        "max_queries": args.queries,
        "strict_4xx": args.strict_4xx,
    }
    findings = detector.detect(records, cfg)
    stats = detector.stat_records(records)

    # ---------- ⑤ 输出 ----------
    print()
    print(f"  输入 {len(lines)} 行 → 合并成 {len(records)} 个请求"
          f"（{skipped} 行不属于任何请求，已跳过：启动期日志 / 静态资源编译）")
    print()
    report.print_summary(records, stats, findings, title=title)

    if args.all:
        info = [f for f in findings if f["severity"] not in ("High", "Medium")]
        if info:
            print(f"  信息级明细（{len(info)} 条）")
            for f in info:
                print(f"      L{f['record']['lineno']:<5} {f['title']}：{f['detail'][:88]}")
            print()

    if not args.no_bugs:
        bug_paths = report.write_bug_files(findings, args.out)
        summary_path = report.write_report_md(records, stats, findings,
                                              os.path.join(args.out, "summary.md"))
        print(f"  缺陷单 {len(bug_paths)} 张 → {args.out}")
        if bug_paths:
            print(f"      首张：{os.path.basename(bug_paths[0])}")
        print(f"  汇总报告 → {summary_path}")

    if args.json:
        out = [{k: v for k, v in r.items() if k != "raw"} | {"raw": r["raw"]} for r in records]
        with open(args.json, "w", encoding="utf-8") as fp:
            json.dump(out, fp, ensure_ascii=False, indent=2)
        print(f"  请求记录 JSON → {args.json}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
