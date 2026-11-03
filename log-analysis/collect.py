# -*- coding: utf-8 -*-
"""采集层：把 Redmine 日志拿到手，统一成 [(行号, 原文), ...] 的形式。

为什么要单独一层：Redmine 官方镜像**不写日志文件**，`log/production.log` 是空的，
Rails 的 logger 直接输出到容器 stdout。所以"日志在哪"这件事本身就有三种答案：

    ① docker logs <容器名>      —— 官方镜像的默认形态（本层 read_docker）
    ② 日志文件                  —— 如果自己改过配置或用宿主机的 nginx（read_file）
    ③ 标准输入                  —— 方便 `docker logs ... | python analyze.py -`（read_stdin）

本层只做一件事：把字节流变成"带行号的行列表"。不解析、不判断、不加工。
所有语义解析都在 parse_rails.py —— 这样换日志格式时只需替换解析层。
"""
import os
import subprocess
import sys


def read_file(path):
    """读一个日志文件，按行返回。

    Args:
        path (str): 日志文件路径。

    Returns:
        list[tuple[int, str]]: [(行号, 行内容), ...]，行号从 1 开始。

    编码用 utf-8 + errors="replace"：Rails 日志里会混入中文参数值、偶发非 UTF-8
    字节，严格解码会直接抛异常中断整次分析。宁可替换成 � 也不要中断。
    """
    records = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f, start=1):
            records.append((i, line.rstrip("\r\n")))
    return records


def read_stdin():
    """从标准输入读日志（管道用法：docker logs xxx | python analyze.py -）。

    Returns:
        list[tuple[int, str]]: 同 read_file()。
    """
    records = []
    for i, line in enumerate(sys.stdin, start=1):
        records.append((i, line.rstrip("\r\n")))
    return records


def read_docker(container, since=None, tail=None):
    """调用 docker logs 取容器日志。

    Args:
        container (str): 容器名，如 "redmin_test-redmine-1"。
        since (str | None): 只取这段时间之后的日志，格式同 docker（"10m" / "2026-11-03T13:00:00"）。
        tail (int | None): 只取最后 N 行。

    Returns:
        list[tuple[int, str]]: 同 read_file()。

    Raises:
        RuntimeError: docker 命令不存在，或容器不存在/未启动。
            这种情况下命令行会给出原始错误，不做二次包装。

    注意 `stderr=subprocess.STDOUT`：Rails 的日志走的是 **stderr**，
    只抓 stdout 会得到一片空白 —— 这是最容易踩的一个坑。
    """
    cmd = ["docker", "logs"]
    if since:
        cmd += ["--since", since]
    if tail:
        cmd += ["--tail", str(tail)]
    cmd.append(container)

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,      # Rails 写 stderr，必须合并
            timeout=300,
        )
    except FileNotFoundError:
        raise RuntimeError("找不到 docker 命令，确认 Docker Desktop 已启动并在 PATH 里")
    except subprocess.TimeoutExpired:
        raise RuntimeError("docker logs 超时（300 秒），用 --since 或 --tail 缩小范围")

    if proc.returncode != 0:
        raise RuntimeError(f"docker logs 失败：{proc.stdout.decode('utf-8', 'replace')[:300]}")

    text = proc.stdout.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return [(i, strip_compose_prefix(line)) for i, line in enumerate(lines, start=1)]


def strip_compose_prefix(line):
    """剥掉 `docker compose logs` 加的容器名前缀。

    `docker logs <容器名>` 单容器输出**不带**前缀，但 `docker compose logs` 会加：

        redmine-1  | I, [2026-11-03T13:59:50.134426 #1]  INFO -- : ...

    带前缀的行会匹配不上 Rails 正则，整份日志一行都解析不出来。
    这里做一次防御：形如 `名字  | 正文` 就切掉，其余原样返回。

    Args:
        line (str): 一行原始日志。

    Returns:
        str: 去掉前缀后的正文；不像 compose 前缀则原样返回。
    """
    idx = line.find("  | ")
    if 0 < idx < 60 and " " not in line[:idx].strip():
        return line[idx + 4:]
    return line
