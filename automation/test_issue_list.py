# -*- coding: utf-8 -*-
"""
列表与过滤用例 —— 对应《4.接口测试用例设计.md》API-62 ~ API-69

这组主要是验证「边界参数」和「无效过滤条件」的处理，
其中 API-69 的结果反直觉：过滤一个不存在的项目，返回的是 404 而不是空列表。
"""

import pytest

from config import PROJECT_ID


def test_api_62_default_list(admin):
    """API-62【正向-必选 P0】默认列表 → 200，返回 issues 数组"""
    resp = admin.list_issues()
    assert resp.status_code == 200
    body = resp.json()
    assert "issues" in body
    assert isinstance(body["issues"], list)


def test_api_63_filter_all_statuses(admin):
    """API-63【正向-组合 P1】?status_id=* 取含已关闭的全部 → 200"""
    resp = admin.list_issues(status_id="*")
    assert resp.status_code == 200
    assert "issues" in resp.json()


def test_api_64_filter_by_project(admin):
    """API-64【正向-组合 P2】按项目过滤 → 200，返回的都属于该项目"""
    resp = admin.list_issues(project_id=PROJECT_ID, limit=50)
    assert resp.status_code == 200
    for issue in resp.json()["issues"]:
        assert issue["project"]["id"] == PROJECT_ID


def test_api_65_pagination(admin):
    """API-65【正向-组合 P2】分页 limit=5&offset=0 → 200，条数不超过 5"""
    resp = admin.list_issues(limit=5, offset=0)
    assert resp.status_code == 200
    assert len(resp.json()["issues"]) <= 5


@pytest.mark.parametrize("params", [
    pytest.param({"limit": 101}, id="API-66-limit超上限"),
    pytest.param({"limit": 0}, id="API-67-limit为零"),
    pytest.param({"offset": -1}, id="API-68-offset为负"),
])
def test_api_66_to_68_boundary_params(admin, params):
    """API-66~API-68【反向-边界值 P2/P3】分页参数越界 → 200（容错处理，不报错）"""
    resp = admin.list_issues(**params)
    assert resp.status_code == 200


def test_api_69_filter_nonexistent_project(admin):
    """
    API-69【反向-功能异常 P1】过滤一个不存在的项目 → 404（不是空列表 200）

    这条和 API-67（limit=0 → 200）放在一起看，说明同一个接口里
    「参数无效」的处理方式并不统一 —— 接口测试要专门盯这类不一致。
    """
    assert admin.list_issues(project_id=999).status_code == 404
