# Redmine 日志分析器

把 Redmine（Rails）的多行日志还原成「请求」，按 6 条规则找出**出了问题的请求**，
每条问题生成一张可以直接贴进 Redmine 的 Markdown 缺陷单。

零第三方依赖，只用 Python 标准库。

---

## 为什么不能直接用普通日志分析工具

普通日志工具假设 **1 行 = 1 条记录**（nginx、syslog 都是这样）。Redmine 不是：

```
I, [2026-11-03T13:59:50.134426 #1]  INFO -- : [321094fe-...] Started GET "/issues/293.json" for 172.18.0.1 ...
I, [...] [321094fe-...] Processing by IssuesController#show as JSON
I, [...] [321094fe-...]   Parameters: {"id" => "293"}
I, [...] [321094fe-...]   Current user: admin (id=1)
I, [...] [321094fe-...] Completed 200 OK in 80ms (Views: 9.9ms | ActiveRecord: 52.8ms (15 queries, 0 cached) | GC: 1.2ms)
```

一个请求占 5 行，出异常时再叠一段调用栈。同一请求的所有行共用 `[request_id]`。

**实测后果**（用「一行一记录」的方式硬跑 500 行真实日志）：

| 指标 | 逐行处理 | 按 request_id 合并 |
|---|---|---|
| 记录数 | 500 | **24** |
| 模板数 | 457 | 11 |
| 压缩比 | **1.0**（聚类完全不工作） | 1.6 |
| 检出问题 | **0** | **4** |

逐行处理时连 403/404/422 都找不到 —— 因为 Rails 把状态码写在 `Completed 404 Not Found`
里，整行**不带任何 ERROR / failed / denied 关键字**，靠关键字匹配的规则一条都命中不了。

第二个关键差异：**堆栈行没有时间戳和级别前缀**，只有 uuid。

```
F, [2026-11-03T13:49:53.183424 #1] FATAL -- : [bd4cca84-...]
[bd4cca84-...] ActionDispatch::Http::Parameters::ParseError (Error occurred while parsing request parameters):
[bd4cca84-...] Causes:
[bd4cca84-...] JSON::ParserError (unexpected token at '{bad json')
[bd4cca84-...] app/controllers/application_controller.rb:737:in 'ApplicationController#api_request?'
```

所以解析层必须认两种行形态，这也是本项目存在的主要理由。

---

## 架构

四层，每层只干一件事，换日志格式只需要换解析层。

```
collect.py            采集：文件 / docker logs / stdin  →  [(行号, 原文)]
    │                 （只管拿数据，不解析）
    ▼
parse_rails.py        解析：按 [request_id] 把多行合并成「请求记录」
    │                 抽出 method / path / status / 耗时 / SQL 条数 / controller / user 等 12 个字段
    ▼
detect.py             检测：6 条规则 × 每个请求 → 待确认问题列表
    │
    ▼
report.py             输出：控制台概览 + 缺陷单 .md + 汇总报告 .md
```

`analyze.py` 是命令行入口，把四层串起来。

### 各文件函数

**collect.py — 采集层**

| 函数 | 作用 |
|---|---|
| `read_file(path)` | 读日志文件，返回 `[(行号, 行)]`。utf-8 + `errors="replace"`，坏字节不中断分析 |
| `read_docker(container, since, tail)` | 调 `docker logs` 取容器日志。**必须 `stderr=STDOUT`**，Rails 写的是 stderr |
| `read_stdin()` | 读标准输入，支持 `docker logs xxx 2>&1 \| python analyze.py -` |
| `strip_compose_prefix(line)` | 剥掉 `docker compose logs` 加的 `容器名  \| ` 前缀，不剥则一行都解析不出来 |

**parse_rails.py — 解析层（核心）**

| 函数 | 作用 |
|---|---|
| `is_rails_log(lines)` | 抽前 200 行算命中率，>5% 判定为 Rails 日志。不是就直接拒绝，避免输出「0 个问题」误导人 |
| `to_epoch(ts)` | `2026-11-03T13:59:50.134426` → Unix 秒。**按 UTC 解析**（容器时区是 UTC，和本地差 8 小时） |
| `merge(lines)` | **主函数**。按 request_id 归组，输出 `(请求记录列表, 被丢弃行数)` |
| `_apply_body(g, body)` | 解析单行正文，把字段写进记录（内部） |
| `_finalize(g)` | 收尾：生成一行可读摘要 `raw`、抽异常类名 `error_kind`、标 `truncated`（内部） |
| `_new_group(...)` | 建空记录，12 个字段在这里一次列全（内部） |

**detect.py — 检测层**

| 函数 | 规则 | 严重度 |
|---|---|---|
| `rule_status_5xx` | 5xx 服务端错误 | High |
| `rule_exception` | 请求内有 FATAL 行 / 异常类名（带调用栈） | High |
| `rule_incomplete` | 有 Started 没 Completed（请求被中断） | High |
| `rule_status_4xx` | 4xx，**默认只统计不报缺陷** | Info（`--strict-4xx` 升 Medium） |
| `rule_slow` | 单请求耗时 > 阈值（默认 500ms） | Medium |
| `rule_many_queries` | 单请求 SQL 条数 > 阈值（默认 40） | Medium |

| 函数 | 作用 |
|---|---|
| `detect(records, cfg)` | 对每个请求跑完 6 条规则，按严重度排序输出；同一请求已报 High/Medium 的不再重复列 4xx 信息条 |
| `stat_records(records)` | 统计口径：状态码分布、P50/P95、最慢 top5、SQL 条数 top5、按控制器聚合 |

**report.py — 输出层**

| 函数 | 作用 |
|---|---|
| `print_summary(...)` | 控制台概览：状态码分布 / 问题清单 / 最慢 top3 / 信息级条目 |
| `write_bug_files(...)` | 每个问题一张 `.md` 缺陷单，含字段表 + 日志原文 + 排查建议 |
| `write_report_md(...)` | 汇总报告：5 张表（状态码 / 问题 / 慢请求 / SQL / 控制器） |
| `fmt_ts` / `fmt_ms` | 时间格式化（统一标 UTC）/ 毫秒去尾零 |

---

## 用法

```bash
# 分析内置真实样本（500 行，24 个请求，含 2 条异常堆栈）
python analyze.py sample/redmine.log

# 直接从容器取（官方镜像不写日志文件，这是主用法）
python analyze.py --docker redmin_test-redmine-1
python analyze.py --docker redmin_test-redmine-1 --since 30m

# 管道
docker logs redmin_test-redmine-1 2>&1 | python analyze.py -

# 调阈值：把慢请求线收紧到 300ms、SQL 线收紧到 25 条
python analyze.py sample/redmine.log --slow 300 --queries 25

# 4xx 也算问题（默认只统计）
python analyze.py sample/redmine.log --strict-4xx
```

| 参数 | 作用 |
|---|---|
| `--slow 500` | 慢请求阈值（毫秒） |
| `--queries 40` | 单请求 SQL 条数阈值 |
| `--strict-4xx` | 把 4xx 从信息级升级为问题 |
| `--all` | 控制台也打印信息级明细 |
| `--no-bugs` | 只打印，不生成缺陷单 |
| `--json out.json` | 导出解析后的请求记录 |

输出：

```
reports/bug-01-exception-L464.md   每条问题一张缺陷单
reports/summary.md                 汇总报告
```

---

## 实测结果（sample/redmine.log，真实容器日志）

```
输入 500 行 → 合并成 24 个请求（366 行不属于任何请求，已跳过）
状态码  200×13  201×1  204×3  400×2  403×1  404×2  422×2
响应    P50 80ms  P95 538ms  平均 175.4ms

检出问题 4 条

[高] 服务端异常  POST /issues.json  400  ← 起因 JSON::ParserError
[高] 服务端异常  POST /issues.json  400  ← 起因 JSON::NestingError
[中] 响应过慢    GET /issues.json?project_id=1&limit=20  1463ms（SQL 540ms 占 37%）
[中] 响应过慢    DELETE /issues/1676.json  538ms（SQL 454ms 占 84%）
```

几个只有看日志才能发现的点：

- **`Completed 400` 配 `F FATAL`**：HTTP 状态码说"客户端发错了"，服务端却抛了完整异常栈。
  只看状态码会漏掉，只看 ERROR 关键字又找不到 403/404。
- **`halted_by=require_admin`**：403 的请求日志里直接写着被哪个过滤器拦下，
  比读代码猜权限逻辑快得多。这类请求耗时 5ms —— 拦在查库之前。
- **同一个 `GET /issues.json?limit=20`，一条 1463ms、一条 82ms，SQL 条数都是 33**。
  SQL 条数一样、耗时差 17 倍 → 不是 N+1，是锁竞争或缓冲池冷热。

---

## 局限

- **只处理 Redmine/Rails 格式**，nginx 那类单行日志会被直接拒绝（不是静默出 0 条）。
- **服务重启会清空日志**：官方镜像写 stdout，`docker compose up -d --force-recreate` 后旧日志就没了，
  要留证据得先 `docker logs > 文件` 落盘。
- **`Starting` 里有并发交错**：真正高并发时同一对 Started/Completed 可能被别的请求插在中间，
  这里按 request_id 归组所以不受影响，但**同一请求内的行序**依赖日志顺序。
- **`4xx` 默认不算问题**是刻意的：这个项目被测对象是 Redmine，做越权/负向测试时 403/404/422
  本来就是预期结果。全报出来只会制造误报。
- **判定阈值（500ms / 40 条 SQL）是按本机实测水位定的**，换机器要重调。
