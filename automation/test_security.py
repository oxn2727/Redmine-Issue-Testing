# -*- coding: utf-8 -*-
"""
安全测试用例（业务安全部分）—— 对应《4.接口测试用例设计.md》API-82 ~ API-87

分工说明：
    攻击安全（木马/病毒/黑客）由专业安全工程师负责，不在功能测试范围内；
    业务安全（敏感数据、越权、注入）是功能测试的职责，就是本文件的内容。

注意：SQL 注入 / XSS 这两条，正确预期是「数据被原样存储、不当代码执行」，
      而不是"接口必须报错"。判断有没有漏洞，要看响应内容和回读的数据。
"""

import requests

from config import BASE_URL, PROJECT_ID, STATUS_IN_PROGRESS


def test_api_82_no_sensitive_data_leak(admin):
    """
    API-82【业务安全 P1】用户接口不泄露敏感数据

    期望响应里没有密码、密码哈希、盐值、API Key。

    ⚠️ 写这条用例踩过的坑：一开始用 "passwd" 做关键词，结果误报 ——
    响应里的 passwd_changed_on 是「密码最后修改时间」，是合法的普通字段。
    **关键词检查要精确到"密码值"，不能拿子串去撞字段名。**
    """
    resp = admin.list_users()
    assert resp.status_code == 200
    body = resp.text.lower()

    for keyword in ("password", "hashed_password", "salt", "api_key", "auth_source"):
        assert keyword not in body, f"响应里出现了敏感字段 {keyword}"

    # 该有的基本字段还在（证明接口是正常工作的，不是刚好返回空）
    first = resp.json()["users"][0]
    assert "login" in first


def test_api_83_unauthorized_access():
    """
    API-83【业务安全 P0】未授权访问

    ⚠️ 实测纠正了一个想当然的判断：**并不是所有接口匿名访问都该 401**。

    实测结果：
        /issues.json     → 200  匿名可读（Anonymous 角色有 view_issues）
        /projects.json   → 200  匿名可读
        /users.json      → 401  需要认证
        /time_entries.json → 401 需要认证

    这是 Redmine 的**设计**：公开项目的列表和详情对匿名开放（方便外部查看），
    但用户信息、工时这类敏感数据必须登录。
    所以这条用例的正确写法是「分组断言」，而不是"一律 401"。
    """
    # 公开数据：匿名可读，200 不是漏洞
    for path in ("/issues.json", "/projects.json"):
        resp = requests.get(f"{BASE_URL}{path}", timeout=15)
        assert resp.status_code == 200, f"{path} 应当允许匿名读取"

    # 受保护数据：匿名访问必须被拒
    for path in ("/users.json", "/time_entries.json"):
        resp = requests.get(f"{BASE_URL}{path}", timeout=15)
        assert resp.status_code == 401, f"{path} 匿名竟然能访问（{resp.status_code}）"


def test_api_84_idor_horizontal_privilege(reporter, admin, unique):
    """
    API-84【业务安全 P1】越权访问（IDOR）：改别人 Issue 的 id 直接操作

    界面上没有按钮，但接口上 id 是明文，改个数字就能试。
    这组验证后端是否独立做了权限校验（而不是依赖前端隐藏按钮）。
    """
    created = admin.create_issue(project_id=PROJECT_ID, subject=f"API-84 IDOR 靶子-{unique}")
    iid = created.json()["issue"]["id"]
    try:
        # 读：reporter1 能读到别人的 Issue（项目成员本来就该能看）
        assert reporter.get_issue(iid).status_code == 200

        # 改：无权，返回 204 但数据不变
        reporter.update_issue(iid, subject="IDOR 篡改")
        assert admin.read_field(iid, "subject") == f"API-84 IDOR 靶子-{unique}"

        # 删：无权，明确 403
        assert reporter.delete_issue(iid).status_code == 403
    finally:
        admin.delete_issue(iid)


def test_api_85_sql_injection(admin, unique):
    """
    API-85【业务安全 P1】SQL 注入探测

    把经典注入串放进字段。正确结果是：被当作普通字符串原样保存，
    既不报数据库错误、也不产生额外影响（Redmine 用 ORM 参数化查询）。
    """
    payload = f"' OR '1'='1' -- {unique}"
    resp = admin.create_issue(project_id=PROJECT_ID, subject=payload)
    assert resp.status_code == 201, "注入串应当被当普通文本接受，而不是触发数据库错误"

    iid = resp.json()["issue"]["id"]
    try:
        # 回读：存进去的是原文，没有被 SQL 解析
        assert admin.read_field(iid, "subject") == payload

        # 数据库表还在（没有因为注入串被 DROP）
        assert admin.list_issues(limit=1).status_code == 200
    finally:
        admin.delete_issue(iid)


def test_api_86_xss_probe(admin, unique):
    """
    API-86【业务安全 P2】XSS 探测

    接口层只负责"存", 正确预期是原样存储（转义是渲染时的事，界面上另有用例）。
    这样断言的意义：证明接口没有把脚本标签静默丢弃，也没有去执行它。
    """
    payload = f"<script>alert('{unique}')</script>"
    resp = admin.create_issue(project_id=PROJECT_ID, subject=payload)
    assert resp.status_code == 201
    iid = resp.json()["issue"]["id"]
    try:
        assert admin.read_field(iid, "subject") == payload
    finally:
        admin.delete_issue(iid)


def test_api_87_privilege_escalation(clients, unique):
    """API-87【业务安全 P1】权限提升：低权限账号访问高权限接口 → 403"""
    # /users.json 只有管理员能看
    for role in ("reporter1", "developer1", "manager1"):
        assert clients[role].list_users().status_code == 403

    # 低权限用户把自己“升级”成管理员：状态类字段里没有这种口子，
    # 这里用「试图修改他人 Issue 的状态」代表提权尝试，应当无效
    from api_client import RedmineAPI
    from config import KEYS
    admin = RedmineAPI(BASE_URL, KEYS["admin"])
    created = admin.create_issue(project_id=PROJECT_ID, subject=f"API-87 提权靶子-{unique}")
    iid = created.json()["issue"]["id"]
    try:
        clients["reporter1"].update_issue(iid, status_id=STATUS_IN_PROGRESS)
        assert admin.read_field(iid, "status", "name") == "New", "reportor1 不该能改他人状态"
    finally:
        admin.delete_issue(iid)
