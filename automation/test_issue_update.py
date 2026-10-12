# -*- coding: utf-8 -*-
"""
更新 Issue 用例 —— 对应《4.接口测试用例设计.md》API-43 ~ API-55

★ 这是整个接口测试里最重要的一组 ★

因为 Redmine 的更新接口有一个反直觉的行为：
    无权修改 / 非法状态转移时，接口返回 204（听起来是"成功"），但数据一点没变。
    所以本文件里的越权和工作流用例，全部采用「改 → 回读 → 比对」的写法，
    而不是简单的 assert resp.status_code == 204。

只断言状态码的测试，会把这几条越权用例全部误判为"通过"。
"""

from config import PROJECT_ID, STATUS_CLOSED, STATUS_IN_PROGRESS, STATUS_RESOLVED


# ======================================================================
# 正向
# ======================================================================

def test_api_43_update_subject(admin, temp_issue, unique):
    """API-43【正向-必选 P0】改标题 → 204，回读标题已变（注意是 204 不是 200）"""
    iid = temp_issue(subject=f"API-43 改之前-{unique}")
    new_title = f"API-43 改之后-{unique}"

    resp = admin.update_issue(iid, subject=new_title)
    # Redmine 更新成功返回 204 No Content，不是 200
    assert resp.status_code == 204
    assert admin.read_field(iid, "subject") == new_title


def test_api_44_add_note(admin, temp_issue, unique):
    """API-44【正向-组合 P1】加注释 → 204，回读 journals 里能找到这条注释"""
    iid = temp_issue(subject=f"API-44 注释-{unique}")
    note = f"这是一条接口测试注释-{unique}"

    assert admin.update_issue(iid, notes=note).status_code == 204

    resp = admin.get_issue(iid, include="journals")
    notes = [j.get("notes", "") for j in resp.json()["issue"].get("journals", [])]
    assert any(note in n for n in notes), f"注释没入库，实际 journals={notes}"


def test_api_45_legal_transition(developer, temp_issue, unique):
    """API-45【正向-组合 P1】合法状态转移 New→In Progress（developer1）→ 204 且生效"""
    iid = temp_issue(subject=f"API-45 合法转移-{unique}")
    assert developer.update_issue(iid, status_id=STATUS_IN_PROGRESS).status_code == 204
    assert developer.read_field(iid, "status", "name") == "In Progress"


def test_api_46_update_multi_fields(admin, temp_issue, unique):
    """API-46【正向-全部参数 P1】一次改多个字段 → 204，三个字段都变"""
    iid = temp_issue(subject=f"API-46 多字段-{unique}")
    new_title = f"API-46 改完-{unique}"

    assert admin.update_issue(iid, subject=new_title, priority_id=3,
                              due_date="2026-12-31").status_code == 204

    data = admin.get_issue(iid).json()["issue"]
    assert data["subject"] == new_title
    assert data["priority"]["name"] == "High"
    assert data["due_date"] == "2026-12-31"


# ======================================================================
# 反向 —— 这几条是本文档的核心价值所在
# ======================================================================

def test_api_47_illegal_transition_blocked(developer, temp_issue, unique):
    """
    API-47【反向-功能异常 P1】⚠️ 核心用例

    developer1 在 New 状态下尝试改成 Closed（跳步）。
    工作流里这条转移没勾选，所以应当被拦住。

    注意断言写法：不能只看"返回 204"就认为成功，
    必须回读状态 —— 实测结果是「返回 204，但状态仍然是 New」。
    """
    iid = temp_issue(subject=f"API-47 非法转移-{unique}")
    before = developer.read_field(iid, "status", "name")
    assert before == "New"

    resp = developer.update_issue(iid, status_id=STATUS_CLOSED)
    # 接口照样返回 204，看起来"成功"了
    assert resp.status_code == 204

    after = developer.read_field(iid, "status", "name")
    assert after == "New", (
        f"⚠️ 非法转移居然生效了（{before} → {after}），说明工作流没拦住！"
    )


def test_api_48_update_others_with_permission(developer, temp_issue, unique):
    """API-48【正向 P1】developer1 改「别人的」Issue 标题 → 204 且生效（有 edit_issues 权限）"""
    iid = temp_issue(subject=f"API-48 他人单-{unique}")   # author 是 admin
    new_title = f"API-48 被 developer 改了-{unique}"

    assert developer.update_issue(iid, subject=new_title).status_code == 204
    assert developer.read_field(iid, "subject") == new_title


def test_api_49_update_others_without_permission(reporter, temp_issue, unique):
    """
    API-49【反向-越权 P1】⚠️ 核心用例

    reporter1 没有 edit_issues 权限，改 admin 提的 Issue 应当失败。
    实测：接口返回 204（假装成功），但标题没有变。
    """
    original = f"API-49 管理员提的单-{unique}"
    iid = temp_issue(subject=original)

    resp = reporter.update_issue(iid, subject="reporter1 篡改的标题")
    assert resp.status_code == 204, "实测：越权修改不会报错，而是静默忽略"

    after = reporter.read_field(iid, "subject")
    assert after == original, f"⚠️ 越权修改生效了（{original} → {after}）！"


def test_api_50_update_own_without_edit_all(reporter, admin, unique):
    """API-50【正向-越权边界 P1】reporter1 改「自己提的」Issue → 204 且生效（有 edit_own_issues）"""
    created = reporter.create_issue(project_id=PROJECT_ID,
                                    subject=f"API-50 reporter 自己的单-{unique}")
    assert created.status_code == 201
    iid = created.json()["issue"]["id"]
    new_title = f"API-50 reporter 自己改了-{unique}"
    try:
        assert reporter.update_issue(iid, subject=new_title).status_code == 204
        assert reporter.read_field(iid, "subject") == new_title
    finally:
        # reporter 没有删除权限，用 admin 收尾
        admin.delete_issue(iid)


def test_api_51_update_not_exist(admin):
    """API-51【反向-功能异常 P1】更新不存在的 Issue → 404"""
    assert admin.update_issue(999999, subject="不存在").status_code == 404


def test_api_52_update_empty_subject(admin, temp_issue):
    """API-52【反向-数据异常 P1】把标题改成空串 → 422"""
    iid = temp_issue(subject="API-52 原本有标题")
    assert admin.update_issue(iid, subject="").status_code == 422


def test_api_53_update_invalid_done_ratio(admin, temp_issue):
    """API-53【反向-数据异常 P2】done_ratio 改成 200（越界）→ 422"""
    iid = temp_issue(subject="API-53 进度越界")
    assert admin.update_issue(iid, done_ratio=200).status_code == 422


def test_api_54_update_empty_body(admin, temp_issue):
    """API-54【反向-参数异常(无参) P3】空 body → 204（没有字段要改，视为幂等成功）"""
    iid = temp_issue(subject="API-54 空 body")
    assert admin.update_issue(iid).status_code == 204


def test_api_55_update_unknown_field(admin, temp_issue):
    """API-55【反向-参数异常(多参) P3】body 带未知字段 → 204（多余字段被忽略）"""
    iid = temp_issue(subject="API-55 多余字段")
    assert admin.update_issue(iid, __bogus__="x").status_code == 204
    # 确认没有把无关字段改坏
    assert admin.get_issue(iid).status_code == 200
