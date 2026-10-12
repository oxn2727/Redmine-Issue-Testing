# -*- coding: utf-8 -*-
"""
pytest 的公共配置与 fixture（固件）。

「fixture」是 pytest 的核心概念：一段"准备工作"，测试函数把它写成参数就能拿到结果，
测试跑完 pytest 会自动执行清理（yield 之后的代码）。比起在每个用例里重复 setUp/tearDown 干净得多。
"""

import time

import pytest

from api_client import RedmineAPI
from config import BASE_URL, KEYS, PROJECT_ID

# scope="session"：整个测试会话只建一次，四个账号的客户端复用
# 参数化的 client，想按角色取客户端就写 @pytest.mark.parametrize("role", [...]) 再用 client_for


@pytest.fixture(scope="session")
def clients():
    """所有角色的客户端，一次性建好：{"admin": RedmineAPI, "reporter1": ...}"""
    return {role: RedmineAPI(BASE_URL, key) for role, key in KEYS.items()}


@pytest.fixture(scope="session")
def admin(clients):
    """管理员客户端（默认就用它，权限最全）"""
    return clients["admin"]


@pytest.fixture(scope="session")
def reporter(clients):
    """报告者客户端 reporter1"""
    return clients["reporter1"]


@pytest.fixture(scope="session")
def developer(clients):
    """开发者客户端 developer1"""
    return clients["developer1"]


@pytest.fixture(scope="session")
def manager(clients):
    """管理者客户端 manager1"""
    return clients["manager1"]


@pytest.fixture
def temp_issue(admin):
    """
    临时 Issue 工厂：用例里调 make() 拿到一条真实 Issue 的 id，
    用例结束后自动删除，保证「测试不污染环境、可反复运行」。

    用法：
        def test_xxx(temp_issue):
            iid = temp_issue(subject="随便一个标题")   # 已经帮你带上 project_id
            ...                                        # 用完不用管，pytest 自动删
    """
    created = []

    def make(**fields):
        fields.setdefault("project_id", PROJECT_ID)
        fields.setdefault("subject", f"auto-{int(time.time() * 1000)}")
        iid = admin.create_issue_or_fail(**fields)
        created.append(iid)
        return iid

    yield make

    # 清理阶段：已经删过的会返回 404，忽略即可
    for iid in created:
        try:
            admin.delete_issue(iid)
        except Exception:
            pass


@pytest.fixture
def unique():
    """生成一个本次运行唯一的字符串，避免用例之间标题撞车"""
    return f"auto-{int(time.time() * 1000)}-{id(object())}"
