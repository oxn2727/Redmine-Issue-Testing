# -*- coding: utf-8 -*-
"""
创建 Issue 用例 —— 对应《4.接口测试用例设计.md》API-06 ~ API-35

组织方式：
    正向 3 条（必选 / 组合 / 全部参数）各自一个函数，因为参数差别大、要单独断言；
    反向 27 条用 parametrize 打成一张表 —— 它们形状一样（给一组参数、期望被拒绝），
    用参数化既省代码，又能在 pytest 输出里一眼看到哪条参数挂了。

    给 pytest.param 显式写 id="API-xx"，报告里就会显示文档里的用例编号，方便对表填执行记录。
"""

import pytest
import requests

from config import (
    BASE_URL, CATEGORY_FRONTEND, PROJECT_ID, STATUS_NEW, TRACKER_BUG,
    TRACKER_FEATURE, PRIORITY_HIGH, VERSION_V11,
)


# ======================================================================
# 一、正向测试（API-06 ~ API-08）
# ======================================================================

def test_api_06_required_only(admin, temp_issue, unique):
    """API-06【正向-必选参数 P0】只给 project_id + subject → 201"""
    iid = temp_issue(subject=f"API-06 必选参数-{unique}")
    resp = admin.get_issue(iid)
    assert resp.status_code == 200
    data = resp.json()["issue"]
    assert data["subject"] == f"API-06 必选参数-{unique}"
    # 没传的字段应该取默认值
    assert data["status"]["name"] == "New"
    assert data["tracker"]["name"] == "Bug"


def test_api_07_partial_optional(admin, temp_issue, unique):
    """API-07【正向-组合参数 P2】必选 + 部分可选 → 201，且传入字段正确回显"""
    iid = temp_issue(
        subject=f"API-07 组合参数-{unique}",
        tracker_id=TRACKER_FEATURE,
        priority_id=PRIORITY_HIGH,
        description="组合参数用例",
    )
    data = admin.get_issue(iid).json()["issue"]
    assert data["tracker"]["name"] == "Feature"
    assert data["priority"]["name"] == "High"
    assert data["description"] == "组合参数用例"


def test_api_08_all_fields(admin, temp_issue, unique):
    """API-08【正向-全部参数 P1】所有必填 + 所有可选 → 201，全部字段正确回显"""
    parent_id = temp_issue(subject=f"API-08 父任务-{unique}")
    iid = temp_issue(
        subject=f"API-08 全部参数-{unique}",
        tracker_id=TRACKER_BUG,
        status_id=STATUS_NEW,
        priority_id=PRIORITY_HIGH,
        description="全部可选字段都传",
        assigned_to_id=1,
        category_id=CATEGORY_FRONTEND,
        fixed_version_id=VERSION_V11,
        parent_issue_id=parent_id,
        start_date="2026-09-24",
        due_date="2026-10-08",
        estimated_hours=8.5,
        done_ratio=30,
        is_private=False,
    )
    data = admin.get_issue(iid).json()["issue"]
    assert data["category"]["name"] == "前端"
    assert data["fixed_version"]["name"] == "V1.1"
    assert data["parent"]["id"] == parent_id
    assert data["start_date"] == "2026-09-24"
    assert data["due_date"] == "2026-10-08"
    assert data["estimated_hours"] == 8.5
    assert data["done_ratio"] == 30
    assert data["is_private"] is False


# ======================================================================
# 二、反向测试（API-09 ~ API-35）
# ======================================================================
# 表结构：(用例编号, 参数, 期望状态码, 说明)
# 参数里如果出现 {u} 会被替换成本次运行唯一的字符串，避免用例之间互相干扰。

NEGATIVE_CASES = [
    # ---------- 功能异常：格式对、业务不成立 ----------
    pytest.param({"project_id": 99999, "subject": "坏项目"}, 422, id="API-09"),
    pytest.param({"project_id": -1, "subject": "负数项目"}, 422, id="API-10"),
    pytest.param({"project_id": PROJECT_ID, "subject": "坏父任务", "parent_issue_id": 99999}, 422, id="API-11"),
    pytest.param({"project_id": PROJECT_ID, "subject": "坏指派", "assigned_to_id": 99999}, 422, id="API-12"),
    pytest.param({"project_id": PROJECT_ID, "subject": "日期倒置",
                  "start_date": "2026-10-01", "due_date": "2026-09-01"}, 422, id="API-13"),

    # ---------- 数据异常：类型 / 格式不对 ----------
    pytest.param({"project_id": PROJECT_ID, "subject": ""}, 422, id="API-15"),
    pytest.param({"project_id": PROJECT_ID, "subject": "   "}, 422, id="API-16"),
    pytest.param({"project_id": PROJECT_ID, "subject": "c" * 255}, 201, id="API-17"),   # 边界内
    pytest.param({"project_id": PROJECT_ID, "subject": "b" * 256}, 422, id="API-18"),   # 边界外
    pytest.param({"project_id": PROJECT_ID, "subject": "长" * 300}, 422, id="API-19"),
    pytest.param({"project_id": "abc", "subject": "类型错"}, 422, id="API-20"),
    pytest.param({"project_id": PROJECT_ID, "subject": "坏优先级", "priority_id": 999}, 422, id="API-21"),
    pytest.param({"project_id": PROJECT_ID, "subject": "越界进度", "done_ratio": 101}, 422, id="API-24"),
    pytest.param({"project_id": PROJECT_ID, "subject": "负进度", "done_ratio": -5}, 422, id="API-25"),
    pytest.param({"project_id": PROJECT_ID, "subject": "负工时", "estimated_hours": -1}, 422, id="API-27"),
    pytest.param({"project_id": PROJECT_ID, "subject": "坏日期", "start_date": "2026-13-45"}, 422, id="API-28a"),
    pytest.param({"project_id": PROJECT_ID, "subject": "坏日期2", "due_date": "not-a-date"}, 422, id="API-28b"),

    # ---------- 参数异常：结构不对 ----------
    pytest.param({"project_id": PROJECT_ID}, 422, id="API-31"),          # 少参：缺 subject
    pytest.param({"subject": "只有主题"}, 422, id="API-30"),             # 少参：缺 project_id
    pytest.param({"project_id": PROJECT_ID, "subjct": "拼错"}, 422, id="API-32"),
    pytest.param({"projectId": PROJECT_ID, "subject": "驼峰"}, 422, id="API-33"),
    pytest.param({"project_id": PROJECT_ID, "subject": "多余字段", "__bogus__": "x"}, 201, id="API-35"),
]


@pytest.mark.parametrize("fields, expected", NEGATIVE_CASES)
def test_api_09_to_35_create_negative(admin, temp_issue, unique, fields, expected):
    """API-09~API-35【反向】各类非法参数，期望被接口拒绝（或按宽容规则忽略）"""
    # 注意：这里绝不能给 fields 补默认 subject ——
    # API-30/31/32 测的正是「缺 subject」，补上就把用例测废了。
    fields = {k: (v.replace("{u}", unique) if isinstance(v, str) else v) for k, v in fields.items()}
    resp = admin.create_issue(**fields)

    assert resp.status_code == expected, (
        f"期望 {expected}，实际 {resp.status_code}；响应={resp.text[:200]}"
    )
    # 期望成功的那几条（边界内 / 多余字段），记得把新建的数据清掉
    if resp.status_code == 201:
        admin.delete_issue(resp.json()["issue"]["id"])


def test_api_14_duplicate_subject(admin, temp_issue, unique):
    """API-14【反向-功能异常，但预期成功 P2】subject 重名 → 201（Redmine 允许重名）"""
    subject = f"API-14 重名测试-{unique}"
    first = temp_issue(subject=subject)
    resp = admin.create_issue(project_id=PROJECT_ID, subject=subject)
    assert resp.status_code == 201, "Redmine 允许标题重复，这里应当成功"
    admin.delete_issue(resp.json()["issue"]["id"])
    assert admin.get_issue(first).status_code == 200


def test_api_22_status_id_invalid_silently_defaults(admin):
    """
    API-22【反向-数据异常 P1】⚠️ 陷阱用例

    status_id 传不存在的 999，**接口不报错**（201），而是静默替换成默认状态 New。
    对比 API-21：priority_id 传 999 会正常报 422 —— 同一个接口，处理方式不一致。
    """
    resp = admin.create_issue(project_id=PROJECT_ID, subject="API-22 非法状态", status_id=999)
    assert resp.status_code == 201, "实测：Redmine 不校验 status_id 的存在性"
    iid = resp.json()["issue"]["id"]
    try:
        assert admin.read_field(iid, "status", "name") == "New", "非法 status_id 被静默回落为 New"
        assert resp.json()["issue"]["status"]["id"] != 999
    finally:
        admin.delete_issue(iid)


def test_api_23_tracker_id_invalid_silently_defaults(admin):
    """
    API-23【反向-数据异常 P1】⚠️ 陷阱用例

    tracker_id 传不存在的 999，同样不报错，静默替换成默认跟踪标签 Bug。
    """
    resp = admin.create_issue(project_id=PROJECT_ID, subject="API-23 非法跟踪", tracker_id=999)
    assert resp.status_code == 201, "实测：Redmine 不校验 tracker_id 的存在性"
    iid = resp.json()["issue"]["id"]
    try:
        assert admin.read_field(iid, "tracker", "name") == "Bug", "非法 tracker_id 被静默回落为 Bug"
    finally:
        admin.delete_issue(iid)


@pytest.mark.parametrize("ratio", [0, 100])
def test_api_26_done_ratio_boundary_ok(admin, unique, ratio):
    """API-26【反向-边界值 P2】done_ratio 取上下边界 0 / 100 → 201"""
    resp = admin.create_issue(project_id=PROJECT_ID, subject=f"API-26 进度{ratio}-{unique}",
                             done_ratio=ratio)
    assert resp.status_code == 201
    iid = resp.json()["issue"]["id"]
    try:
        assert admin.read_field(iid, "done_ratio") == ratio
    finally:
        admin.delete_issue(iid)


# ----------------------------------------------------------------------
# 结构类异常：请求体不是一个合法的 issue 包装，用裸 requests 发
# ----------------------------------------------------------------------

def test_api_29_empty_body(admin):
    """API-29【反向-参数异常(无参) P2】完全空的 body → 422"""
    resp = requests.post(f"{BASE_URL}/issues.json", headers=admin.headers,
                         json={}, timeout=15)
    assert resp.status_code == 422


def test_api_34_no_issue_wrapper(admin):
    """API-34【反向-参数异常 P2】字段直接放顶层，没包在 issue 里 → 422"""
    resp = requests.post(f"{BASE_URL}/issues.json", headers=admin.headers,
                         json={"project_id": PROJECT_ID, "subject": "没包 issue"}, timeout=15)
    assert resp.status_code == 422


def test_api_p8_malformed_json(admin):
    """
    API-29 补充【反向-数据异常 P2】body 不是合法 JSON → 400

    注意不是 422：Redmine 对「JSON 都解析不了」的请求返回 400 Bad Request，
    和「JSON 能解析但字段不合法」的 422 是两种错误，不要混。
    """
    resp = requests.post(f"{BASE_URL}/issues.json", headers=admin.headers,
                         data="{bad json", timeout=15)
    assert resp.status_code == 400
