# -*- coding: utf-8 -*-
"""
删除 Issue 用例 —— 对应《4.接口测试用例设计.md》API-56 ~ API-61

注意和「更新」的区别：
    无权修改 → 204（静默忽略）
    无权删除 → 403（明确拒绝）
同一个系统两种拒绝方式，这正是接口测试要记录下来的不一致点。
"""

from config import PROJECT_ID


def test_api_56_delete_existing(admin, temp_issue, unique):
    """API-56【正向-必选 P0】删除存在的 Issue → 204，之后查询变 404"""
    iid = temp_issue(subject=f"API-56 待删除-{unique}")
    assert admin.get_issue(iid).status_code == 200

    resp = admin.delete_issue(iid)
    assert resp.status_code == 204, "Redmine 删除成功返回 204（无内容），不是 200"

    # 回读验证：真的删掉了
    assert admin.get_issue(iid).status_code == 404


def test_api_57_delete_not_exist(admin):
    """API-57【反向-功能异常 P1】删除不存在的 Issue → 404"""
    assert admin.delete_issue(999999).status_code == 404


def test_api_58_delete_twice(admin, temp_issue):
    """API-58【反向-功能异常 P2】重复删除（幂等性）→ 第二次 404"""
    iid = temp_issue(subject="API-58 重复删除")
    assert admin.delete_issue(iid).status_code == 204
    assert admin.delete_issue(iid).status_code == 404


def test_api_59_reporter_delete_others(reporter, temp_issue, unique):
    """API-59【反向-越权 P1】reporter1 删除他人 Issue → 403（有权限门，明确报错）"""
    iid = temp_issue(subject=f"API-59 他人单-{unique}")
    assert reporter.delete_issue(iid).status_code == 403


def test_api_60_reporter_delete_own(reporter, admin, unique):
    """API-60【反向-越权 P1】reporter1 删除自己提的 Issue → 403（Reporter 无 delete_issues）"""
    created = reporter.create_issue(project_id=PROJECT_ID,
                                    subject=f"API-60 reporter 自己的单-{unique}")
    iid = created.json()["issue"]["id"]
    try:
        assert reporter.delete_issue(iid).status_code == 403
    finally:
        admin.delete_issue(iid)


def test_api_61_get_does_not_delete(admin, temp_issue):
    """API-61【反向-数据异常 P3】用 GET 访问（不是 DELETE）→ 200，数据仍在"""
    iid = temp_issue(subject="API-61 GET 不会删")
    assert admin.get_issue(iid).status_code == 200
    assert admin.get_issue(iid).status_code == 200   # 再查一次，还在
