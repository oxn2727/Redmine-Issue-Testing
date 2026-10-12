# -*- coding: utf-8 -*-
"""
业务场景用例 —— 对应《4.接口测试用例设计.md》API-70 ~ API-77

「场景测试」= 按用户真实使用流程，连续调用多个接口。
和单接口测试的区别：单接口测的是"这个接口对不对"，场景测的是"接口串起来对不对"。

设计要点（来自方法论）：
  1. 必须在单接口测试全部通过之后再跑；
  2. 一般只设计正向场景（异常已经在单接口层覆盖了）；
  3. 尽量用较少的用例覆盖尽可能多的接口。
"""

from config import (
    PROJECT_ID, STATUS_CLOSED, STATUS_IN_PROGRESS, STATUS_RESOLVED, STATUS_FEEDBACK,
)


def test_api_70_full_lifecycle(admin, manager, unique):
    """
    API-70【场景 P0】缺陷完整生命周期

    创建 → 查询 → 改状态 → 加注释 → 关闭 → 删除 → 再查
    一条场景串起 6 个接口调用，覆盖 POST/GET/PUT/DELETE 四种方法。
    """
    # 第 1 步：创建
    created = admin.create_issue(project_id=PROJECT_ID, subject=f"API-70 生命周期-{unique}")
    assert created.status_code == 201
    iid = created.json()["issue"]["id"]

    # 第 2 步：查询（此时应当是 New）
    assert admin.read_field(iid, "status", "name") == "New"

    # 第 3 步：改状态（用 manager，权限最全）
    assert manager.update_issue(iid, status_id=STATUS_IN_PROGRESS).status_code == 204
    assert manager.read_field(iid, "status", "name") == "In Progress"

    # 第 4 步：加注释
    assert manager.update_issue(iid, notes="已修复，请验证").status_code == 204

    # 第 5 步：关闭
    assert manager.update_issue(iid, status_id=STATUS_CLOSED).status_code == 204
    data = manager.get_issue(iid).json()["issue"]
    assert data["status"]["is_closed"] is True
    assert data["closed_on"] is not None, "关闭后 closed_on 应当有值"

    # 第 6 步：删除
    assert admin.delete_issue(iid).status_code == 204

    # 第 7 步：再查，应当 404
    assert admin.get_issue(iid).status_code == 404


def test_api_71_developer_fix_flow(developer, temp_issue, unique):
    """API-71【场景 P1】开发者修复流程：认领 → 修完 → 加修复说明"""
    iid = temp_issue(subject=f"API-71 开发修复-{unique}")

    # 认领：New → In Progress
    assert developer.update_issue(iid, status_id=STATUS_IN_PROGRESS).status_code == 204
    assert developer.read_field(iid, "status", "name") == "In Progress"

    # 修完：In Progress → Resolved
    assert developer.update_issue(iid, status_id=STATUS_RESOLVED).status_code == 204
    assert developer.read_field(iid, "status", "name") == "Resolved"

    # 留下修复说明
    assert developer.update_issue(iid, notes="已修改空指针问题").status_code == 204


def test_api_72_manager_accept_flow(manager, temp_issue, unique):
    """API-72【场景 P1】管理者验收流程：Resolved → Closed"""
    iid = temp_issue(subject=f"API-72 验收-{unique}")
    manager.update_issue(iid, status_id=STATUS_RESOLVED)
    assert manager.update_issue(iid, status_id=STATUS_CLOSED).status_code == 204

    data = manager.get_issue(iid).json()["issue"]
    assert data["status"]["name"] == "Closed"
    assert data["closed_on"] is not None


def test_api_73_reject_and_reopen_flow(manager, developer, temp_issue, unique):
    """API-73【场景 P1】打回重开流程：Resolved → Feedback（打回）→ In Progress（重开）"""
    iid = temp_issue(subject=f"API-73 打回流程-{unique}")

    # 先走到 Resolved
    manager.update_issue(iid, status_id=STATUS_IN_PROGRESS)
    manager.update_issue(iid, status_id=STATUS_RESOLVED)
    assert manager.read_field(iid, "status", "name") == "Resolved"

    # 验证不通过，打回到 Feedback
    assert manager.update_issue(iid, status_id=STATUS_FEEDBACK).status_code == 204
    assert manager.read_field(iid, "status", "name") == "Feedback"

    # 开发重新处理
    assert developer.update_issue(iid, status_id=STATUS_IN_PROGRESS).status_code == 204
    assert developer.read_field(iid, "status", "name") == "In Progress"


def test_api_74_cross_role_privilege(admin, reporter, manager, unique):
    """
    API-74【场景 P1】越权场景：报告者提单后不能自己关单，只有管理者能关

    这是最贴近真实业务的一条：测试提了 Bug，不能自己把 Bug 关掉。
    """
    created = reporter.create_issue(project_id=PROJECT_ID, subject=f"API-74 越权场景-{unique}")
    assert created.status_code == 201
    iid = created.json()["issue"]["id"]

    # reporter1 想自己关闭 —— 返回 204 但不生效
    resp = reporter.update_issue(iid, status_id=STATUS_CLOSED)
    assert resp.status_code == 204
    assert reporter.read_field(iid, "status", "name") == "New", "报告者不该能关单"

    # manager1 关闭 —— 成功
    assert manager.update_issue(iid, status_id=STATUS_CLOSED).status_code == 204
    assert manager.read_field(iid, "status", "name") == "Closed"

    admin.delete_issue(iid)


def test_api_75_subtask_flow(admin, temp_issue, unique):
    """API-75【场景 P2】子任务场景：父任务 → 子任务，父子关系正确"""
    parent_id = temp_issue(subject=f"API-75 父任务-{unique}")
    child_id = temp_issue(subject=f"API-75 子任务-{unique}", parent_issue_id=parent_id)

    child = admin.get_issue(child_id).json()["issue"]
    assert child["parent"]["id"] == parent_id


def test_api_76_filter_scenario(admin, temp_issue, unique):
    """API-76【场景 P2】过滤场景：连续建多条 → 按条件过滤 → 结果符合条件"""
    a = temp_issue(subject=f"API-76 A-{unique}")
    b = temp_issue(subject=f"API-76 B-{unique}")
    # 把 B 改成进行中，制造状态差异
    admin.update_issue(b, status_id=STATUS_IN_PROGRESS)

    resp = admin.list_issues(project_id=PROJECT_ID, status_id=STATUS_IN_PROGRESS, limit=100)
    assert resp.status_code == 200
    ids = [i["id"] for i in resp.json()["issues"]]
    assert b in ids, "按 In Progress 过滤应当能查到自己刚改的 Issue"
    assert a not in ids, "还是 New 状态的 Issue 不该出现在 In Progress 结果里"


def test_api_77_history_consistency(admin, temp_issue, unique):
    """API-77【场景 P1】数据一致性：改 3 次后，历史记录条数与最终值都对得上"""
    iid = temp_issue(subject=f"API-77 历史-{unique}")

    for i in range(1, 4):
        assert admin.update_issue(iid, subject=f"API-77 第{i}次修改-{unique}").status_code == 204

    resp = admin.get_issue(iid, include="journals")
    assert resp.status_code == 200
    data = resp.json()["issue"]

    # 最终值 = 最后一次修改
    assert data["subject"] == f"API-77 第3次修改-{unique}"
    # 变更历史：实测「创建」不产生 journal，每次字段变更产生 1 条，改 3 次 = 3 条
    journals = data.get("journals", [])
    assert len(journals) == 3, f"改 3 次应有 3 条变更记录，实际 {len(journals)} 条"
