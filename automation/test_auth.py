# -*- coding: utf-8 -*-
"""
认证接口用例 —— 对应《4.接口测试用例设计.md》API-01 ~ API-05

这一组看起来简单，但 API-05 是接口测试最典型的「越权验证」：
界面上普通用户看不到「管理」菜单，接口上却能直接打 —— 后端防没防，一打便知。
"""

import pytest
import requests

from config import BASE_URL


def test_api_01_valid_key(admin):
    """API-01【正向-必选 P0】正确 Key 访问 /users/current.json → 200"""
    resp = admin.current_user()
    assert resp.status_code == 200
    assert resp.json()["user"]["login"] == "admin"


def test_api_02_wrong_key():
    """API-02【反向-功能异常 P0】错误 Key → 401"""
    resp = requests.get(
        f"{BASE_URL}/users/current.json",
        headers={"X-Redmine-API-Key": "wrong-key-123"},
        timeout=15,
    )
    assert resp.status_code == 401
    # 401 的响应体是空的，所以不能去解析 JSON —— 只断言状态码
    assert resp.text == ""


def test_api_03_missing_key():
    """API-03【反向-参数异常(无参) P0】完全不带头 → 401"""
    resp = requests.get(f"{BASE_URL}/users/current.json", timeout=15)
    assert resp.status_code == 401


def test_api_04_malformed_key():
    """API-04【反向-数据异常 P2】Key 只有 3 个字符 → 401"""
    resp = requests.get(
        f"{BASE_URL}/users/current.json",
        headers={"X-Redmine-API-Key": "abc"},
        timeout=15,
    )
    assert resp.status_code == 401


@pytest.mark.parametrize("role", ["reporter1", "developer1", "manager1"])
def test_api_05_list_users_forbidden(clients, role):
    """API-05【反向-越权 P1】非管理员访问 /users.json → 403"""
    resp = clients[role].list_users()
    assert resp.status_code == 403, f"{role} 竟然能列用户，这是越权漏洞！"


def test_api_05_admin_can_list_users(admin):
    """API-05 对照组：管理员访问 /users.json → 200（证明 403 不是接口本身坏了）"""
    resp = admin.list_users()
    assert resp.status_code == 200
