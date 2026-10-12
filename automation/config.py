# -*- coding: utf-8 -*-
"""
接口测试配置。

改这里的值就能切换环境 / 账号，不用去改测试代码。
也支持用环境变量覆盖（方便 CI 里跑），例如：
    set REDMINE_BASE_URL=http://localhost:3000
"""

import os

# ---------- 被测系统地址 ----------
BASE_URL = os.getenv("REDMINE_BASE_URL", "http://localhost:3000")

# ---------- 各账号的 API Key ----------
# 生成方式见 automation/4.2-接口测试执行步骤.md 1.3，或用 scripts/setup-api-env.rb 自动生成
KEYS = {
    "admin":     os.getenv("REDMINE_KEY_ADMIN",     "37da63d886132084a9174cfc82d8aa71b9b64c4b"),
    "reporter1": os.getenv("REDMINE_KEY_REPORTER",  "7ccb3f452b13be179af51890df67b7155f338f16"),
    "developer1": os.getenv("REDMINE_KEY_DEVELOPER", "2e26af15f157f329150623136aee8c774b672b10"),
    "manager1":  os.getenv("REDMINE_KEY_MANAGER",   "68e4f8f65f56cacef06188684af2221320f4bc02"),
}

# ---------- 测试项目 ----------
PROJECT_ID = 1            # 「电商后台 V1.0」

# ---------- 枚举值（与数据库里的一致）----------
TRACKER_BUG = 1
TRACKER_FEATURE = 2
TRACKER_SUPPORT = 3

STATUS_NEW = 1
STATUS_IN_PROGRESS = 2
STATUS_RESOLVED = 3
STATUS_FEEDBACK = 4
STATUS_CLOSED = 5
STATUS_REJECTED = 6

PRIORITY_LOW = 1
PRIORITY_NORMAL = 2
PRIORITY_HIGH = 3

CATEGORY_FRONTEND = 1     # 问题类别：前端
VERSION_V11 = 1           # 目标版本：V1.1

# ---------- 请求超时（秒）----------
TIMEOUT = 15

# ---------- 不存在的 id（专门用来测"资源不存在"）----------
NOT_EXIST_ID = 999999
