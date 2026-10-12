# -*- coding: utf-8 -*-
"""
Redmine 接口的封装层（也常叫「接口对象层」）。

为什么要有这一层：
    如果不封装，每个测试函数里都要写 base_url + 路径 + 请求头 + json 包装，
    接口一改（比如路径从 /issues.json 变成 /v2/issues）就要改几十处。
    封装之后，测试用例只关心「业务动作」，改接口只改这一个文件。

命名习惯：方法名直接用接口的语义（create_issue / get_issue），不写 get/post 这种技术名。
"""

import requests


class RedmineAPI:
    """一个实例 = 一个账号身份（用该账号的 API Key 发请求）。"""

    def __init__(self, base_url, api_key, timeout=15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # 请求头：Redmine 用 X-Redmine-API-Key 认证，不需要登录态
        self.headers = {
            "X-Redmine-API-Key": api_key,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # 底层：所有请求都走这里，便于统一异常处理 / 日志
    # ------------------------------------------------------------------
    def _request(self, method, path, json_body=None, params=None, headers=None):
        url = f"{self.base_url}{path}"
        h = dict(self.headers)
        if headers:
            h.update(headers)
        resp = requests.request(
            method, url, json=json_body, params=params,
            headers=h, timeout=self.timeout,
        )
        return resp

    # ------------------------------------------------------------------
    # 认证 / 用户
    # ------------------------------------------------------------------
    def current_user(self, **overrides):
        """GET /users/current.json —— 取当前用户（用来验证 Key 是否有效）"""
        return self._request("GET", "/users/current.json", headers=overrides or None)

    def list_users(self):
        """GET /users.json —— 用户列表（仅管理员能访问）"""
        return self._request("GET", "/users.json")

    # ------------------------------------------------------------------
    # Issue：增删改查
    # ------------------------------------------------------------------
    def create_issue(self, **fields):
        """
        创建 Issue。
        必填：project_id、subject；其余见《4.接口测试用例设计.md》2.3 字段字典。
        用法：api.create_issue(project_id=1, subject="标题")
        """
        return self._request("POST", "/issues.json", json_body={"issue": fields})

    def get_issue(self, issue_id, **params):
        """查询 Issue 详情，params 可传 include=journals 等"""
        return self._request("GET", f"/issues/{issue_id}.json", params=params or None)

    def update_issue(self, issue_id, **fields):
        """更新 Issue。注意：成功返回 204，且 204 不代表一定改成功（要回读）"""
        return self._request("PUT", f"/issues/{issue_id}.json", json_body={"issue": fields})

    def delete_issue(self, issue_id):
        """删除 Issue。成功返回 204"""
        return self._request("DELETE", f"/issues/{issue_id}.json")

    def list_issues(self, **params):
        """Issue 列表，params 可传 project_id / status_id / limit / offset 等"""
        return self._request("GET", "/issues.json", params=params or None)

    # ------------------------------------------------------------------
    # 便捷方法
    # ------------------------------------------------------------------
    def create_issue_or_fail(self, **fields):
        """创建成功返回 issue id；失败直接抛异常（fixture 里用）"""
        resp = self.create_issue(**fields)
        assert resp.status_code == 201, f"创建 Issue 失败：{resp.status_code} {resp.text}"
        return resp.json()["issue"]["id"]

    def read_field(self, issue_id, *path):
        """
        回读某个字段的当前值 —— 接口测试的关键动作。

        204 状态码不可信（无权限/非法状态转移时 Redmine 也返回 204 但不改数据），
        所以「改完再读一次」才是唯一能证明改动生效的方法。

        用法：api.read_field(3, "status", "name")  ->  "New"
        """
        resp = self.get_issue(issue_id)
        assert resp.status_code == 200, f"回读失败：{resp.status_code}"
        value = resp.json()["issue"]
        for key in path:
            value = value[key]
        return value
