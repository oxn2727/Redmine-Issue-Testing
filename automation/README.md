# automation —— 接口自动化测试（pytest）

对应用例：`test-cases/3.3-接口用例-87条.md`（API-01 ~ API-87）
执行说明：`4.2-接口测试执行步骤.md`（curl / Postman / pytest 三种方式的完整步骤）

---

## 跑起来

**前提**：Redmine 容器在跑（<http://localhost:3000>），且 `config.py` 里的 4 个 API Key 有效。

```bash
cd automation

# 1) 装依赖（只需一次）
pip install -r requirements.txt

# 2) 跑全部用例 —— 期望 89 passed（约 16 秒）
pytest -v

# 常用变体
pytest -v --collect-only                  # 不执行，只列用例名（对表用）
pytest -v test_issue_update.py            # 只跑"更新"这一个文件
pytest -v -k "api_47 or api_49"           # 只跑含 api_47 / api_49 的用例
pytest -v -k "negative"                   # 只跑反向用例

# 生成 HTML 报告（需先 pip install pytest-html）
pytest --html=report.html --self-contained-html
```

> **`89` 和设计文档里的 `87` 对不上？** 因为有用例参数化了 —— `API-05` 让三个角色各跑一次、`API-37~40` 展开成 4 条。**参数化展开后的条数 = pytest 统计的条数**，属正常现象。

---

## 文件说明

| 文件 | 作用 |
|---|---|
| `config.py` | **唯一的配置文件**：被测地址 / 4 个账号的 API Key / 枚举值常量。支持环境变量覆盖（`REDMINE_BASE_URL`、`REDMINE_KEY_ADMIN`、`REDMINE_KEY_REPORTER`、`REDMINE_KEY_DEVELOPER`、`REDMINE_KEY_MANAGER`） |
| `api_client.py` | 接口封装层 `RedmineAPI`：`create_issue()` / `get_issue()` / `update_issue()` / `delete_issue()` / `list_issues()`，以及**回读方法 `read_field()`** |
| `conftest.py` | pytest fixture：四个角色的客户端（`admin` / `reporter` / `developer` / `manager`）+ 临时 Issue 自动创建与清理 |
| `test_auth.py` | API-01~05　认证与越权访问 |
| `test_issue_create.py` | API-06~35　创建 Issue（正向 3 类 + 反向 27 条） |
| `test_issue_read.py` | API-36~42　查询详情 |
| `test_issue_update.py` | API-43~55　更新（**含 4 条必须回读验证的越权 / 工作流用例**） |
| `test_issue_delete.py` | API-56~61　删除 |
| `test_issue_list.py` | API-62~69　列表与过滤 |
| `test_scenario.py` | API-70~77　业务场景（多接口串联，逐步换角色 Key） |
| `test_security.py` | API-82~87　业务安全 |

---

## 三个必须知道的点

1. **PUT / DELETE 成功返回 204，不是 200**；而且 **204 不代表真的改成功** —— 无权限、非法状态转移时 Redmine 也返回 204，但数据原封不动。
   → 所以工程里凡涉及越权的用例，都用 `read_field()` **回读比对**，而不是只断言状态码。

2. **用例会自己清理数据**。`conftest.py` 的 `temp_issue` fixture 在用例结束后自动删除创建的 Issue，**可以反复跑，不会把环境搞乱**。

3. **API Key 变了要改 `config.py`**。重新部署 Redmine 或重新生成 Key 后，跑一次 `../scripts/setup-api-env.cmd`，或到界面「我的账号 → API 访问键」重新生成。
