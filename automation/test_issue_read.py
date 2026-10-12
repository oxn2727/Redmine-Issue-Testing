# -*- coding: utf-8 -*-
"""
查询 Issue 详情用例 —— 对应《4.接口测试用例设计.md》API-36 ~ API-42

这组主要验证「id 无效时的处理是否一致」：四种无效 id（不存在 / 非数字 / 0 / 负数）
应当统一返回 404，而不是有人 404、有人 500。
"""

import pytest
import requests

from config import BASE_URL


def test_api_36_get_existing(admin, temp_issue, unique):
    """API-36【正向-必选 P0】查询存在的 Issue → 200，字段完整"""
    iid = temp_issue(subject=f"API-36 查询-{unique}")
    data = admin.get_issue(iid).json()["issue"]
    # 逐项检查必要字段都在（字段清单见设计文档 2.3）
    for key in ("id", "project", "tracker", "status", "priority", "author",
                "subject", "created_on", "updated_on"):
        assert key in data, f"响应缺少字段 {key}"


@pytest.mark.parametrize("bad_id", [999999, "abc", 0, -1],
                         ids=["API-37-不存在", "API-38-非数字", "API-39-零", "API-40-负数"])
def test_api_37_to_40_get_invalid_id(admin, bad_id):
    """API-37~API-40【反向】无效 id 一律 404（验证处理一致性）"""
    resp = admin.get_issue(bad_id)
    assert resp.status_code == 404


def test_api_41_include_journals(admin, temp_issue):
    """API-41【正向-组合 P2】带 include 参数 → 200，返回额外的子对象"""
    iid = temp_issue(subject="API-41 include 参数")
    resp = admin.get_issue(iid, include="journals")
    assert resp.status_code == 200
    assert "journals" in resp.json()["issue"]


def test_api_42_xml_format(admin, temp_issue):
    """API-42【正向-组合 P3】用 .xml 后缀 → 200，返回 XML 而非 JSON"""
    iid = temp_issue(subject="API-42 XML")
    resp = requests.get(f"{BASE_URL}/issues/{iid}.xml", headers=admin.headers, timeout=15)
    assert resp.status_code == 200
    assert "<?xml" in resp.text
