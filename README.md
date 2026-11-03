# Redmine Issue 模块测试项目

对开源缺陷跟踪系统 **Redmine 6** 的 **Issue（问题）模块**做一次完整的测试实践：

**需求分析 → 测试计划 → 用例设计 → 执行 → 测试报告**

被测系统由 Docker 在本地自建，**全部用例只针对自有部署实例**，不涉及任何第三方线上系统。

---

## 一、项目概览

| 项 | 内容 |
|---|---|
| **被测对象** | [Redmine 6](https://www.redmine.org/) —— 开源缺陷跟踪 / 项目管理平台（12 个项目级模块 + 10 项管理后台功能） |
| **测试范围** | **只测 Issue 模块**，覆盖 4 个维度：功能 / 状态流转 / 权限 / 接口 |
| **明确不测** | 其余 11 个模块、UI 自动化、跨浏览器兼容、渗透测试、外部认证（LDAP / OAuth） |
| **用例规模** | **156 条** = 界面层 **69** 条（手工）+ 接口层 **87** 条（pytest 自动化） |
| **冒烟集** | **24 条**（界面 17 + 接口 7）—— 每个功能点、每个接口各一条，一遍约 20 分钟 |
| **测试环境** | Docker + Redmine 6 + MySQL 8；4 个账号：`admin` / `reporter1`(Reporter) / `developer1`(Developer) / `manager1`(Manager) |
| **使用工具** | Postman、pytest + requests、curl、Docker |
| **接口自动化** | 87 条用例已全部脚本化，参数化展开为 **89 个测试，全部通过（89 passed）** |

---

## 二、为什么只测一个模块

Redmine 有 12 个项目级模块 + 10 项管理后台功能，**全量普查在有限时间内只能做到"每个模块点两下"**。本项目做了范围收敛，只深耕 Issue 模块：

| 理由 | 说明 |
|---|---|
| **Issue 是系统的存在理由** | Redmine 本质就是缺陷跟踪系统，版本、甘特图、日历都是围着 Issue 转的 |
| **四种测试类型都能落地** | 功能、状态机、权限、接口 —— 一个模块能把四种方法全部用上 |
| **业务流完整** | 提报 → 分派 → 修复 → 验证 → 关闭，整条链可跑通，场景法有用武之地 |
| **权限分层清晰** | Reporter / Developer / Manager 三种角色对同一条 Issue 的权限完全不同，越权测试素材充足 |

---

## 三、目录结构

```
Redmine-Issue-Testing/
├── README.md                                ← 本文件（项目简介 / 怎么跑 / 结果）
├── docs/                                    【输入与方案】
│   ├── 1.1-被测系统简介.md                      系统是什么、有哪些模块、Issue 的业务主线
│   ├── 1.2-需求规格说明书-Issue模块.md            需求规格（FR / BR / NFR + 界面字段清单）
│   ├── 1.3-接口文档-REST-API.md                REST API 规格（端点 / 字段 / 认证 / 官方约定）
│   ├── 2.1-测试计划.md                          范围 / 目标 / 策略 / 环境 / 排期 / 风险
│   ├── 2.2-环境搭建指南.md                       从零把环境跑起来（含踩坑与自检清单）
│   ├── 2.4-测试方案-界面用例设计.md                界面 69 条怎么推出来的（取值池 / 组合规则 / 轮转表）
│   ├── 2.5-测试方案-接口用例设计.md                接口 87 条怎么推出来的（两层设计法 + 实测不一致点）
│   └── 2.6-测试报告.md                         执行情况与实测结果汇总
├── test-cases/                              【交付物：只有用例表】
│   ├── 3.1-冒烟用例.md                          ★ 24 条，先跑这份
│   ├── 3.2-界面用例-Issue模块-69条.md            九要素宽表（编号/模块/标题/优先级/前置/步骤/数据/预期/实际）
│   ├── 3.3-接口用例-87条.md                    每条给完整请求头 + 可原样发送的 JSON + 预期响应
│   └── 4.1-界面用例执行说明.md                    执行顺序 / 记录规范 / 严重程度分级 / 通过率口径
├── automation/                              【自动化：pytest 接口测试】
│   ├── 4.2-接口测试执行步骤.md                    三种执行方式（curl / Postman / pytest）
│   ├── config.py · api_client.py · conftest.py
│   └── test_auth.py · test_issue_*.py · test_scenario.py · test_security.py
├── postman/                                 Postman 集合 + 环境（冒烟 7 条，导入即用）
├── log-analysis/                            【日志分析：读 Redmine 自己的日志出缺陷单】
│   ├── README.md                                架构 / 各函数作用 / 6 条规则 / 局限
│   ├── collect.py · parse_rails.py · detect.py · report.py · analyze.py
│   └── sample/redmine.log                       真实容器日志 500 行（24 请求 / 2 条异常栈）
├── defects/缺陷记录.md                        缺陷提报规范 + 台账（当前为空）
└── scripts/                                 环境复现脚本（docker-compose / seed / 账号 / Key）
```

---

## 四、快速开始

### 1. 起环境（Windows，已有 Docker Desktop）

```bat
cd scripts
start-redmine.cmd      :: 一键：启动 Docker → compose up → 自检（trackers / 角色权限 / 账号可登录）
```

跑完浏览器打开 <http://localhost:3000>，用 `admin / Test@1234` 能登录即成功。
（首次会拉取 mysql + redmine 镜像，需几分钟。手动方式见 `docs/2.2-环境搭建指南.md`。）

### 2. 生成测试数据与 API Key

```bat
cd scripts
setup-api-env.cmd      :: 启用 REST API + 生成 4 个账号的 Key + 配项目成员 / 类别 / 版本（幂等，可重复跑）
```

> **关键前置**：**管理 → 设置 → API → 勾选「启用 REST Web Service」**（上面的脚本会自动做）。
> 不勾选则**所有**接口一律 403 且响应体为空。

### 3. 跑接口自动化

```bash
cd automation
pip install -r requirements.txt
pytest -v              # 期望：89 passed
```

### 4. （可选）跑接口冒烟

Postman 里 `Import` 导入 `postman/` 下两个文件 → 右上角选 `Redmine_Smoke` 环境 → 按 `SM-API-01 → 07` 顺序 Send。
7 条覆盖认证 / 创建 / 查询 / 更新 / 删除 / 列表 / 权限，每条自带断言。

### 5. （可选）分析日志

```bash
cd log-analysis
python analyze.py sample/redmine.log                    # 内置真实样本
python analyze.py --docker <容器名> --since 30m          # 直接读容器（官方镜像不写日志文件）
```

产出 `reports/bug-NN-*.md`（每条问题一张缺陷单）+ `reports/summary.md`（汇总 5 表）。
零第三方依赖，只用标准库。详见 `log-analysis/README.md`。

---

## 五、实际结果

**接口层**（真实执行）

| 项 | 结果 |
|---|---|
| 用例执行 | 87 条用例 → 参数化展开 **89 个测试，全部通过** |
| 认证 | 正确 Key → 200；错误 / 缺失 Key → 401；非管理员访问 `/users.json` → 403（admin → 200） |
| 创建边界 | `subject` 255 → 201、256 → 422；`done_ratio` 0/100 → 201、101/-5 → 422 |
| 更新 / 删除 | 成功返回 **204**（不是 200） |
| 匿名访问 | `/issues.json`、`/projects.json` → **200**；`/users.json`、`/time_entries.json` → **401**（设计如此） |
| 响应时长基线 | `GET /issues.json?limit=20` 连发 10 次：min 38ms / avg 60ms / max 84ms（本地单机，非生产基准） |

**界面层**：69 条用例设计完成，**手工执行记录待补**（填在用例表的「实际结果」列）。

> 设计条数与执行结果是两件事：**设计了 156 条**是事实；**通过率 / 缺陷数**必须跑完才有，本仓库不写未执行的数字。

---

## 六、发现的问题

- **接口层新发现的功能缺陷：0** —— 被测对象是成熟开源项目，本轮做的是**回归性质**的覆盖验证。
- **记录到 2 处接口行为不一致**（属设计层面差异，列入观察项，未作为缺陷提报）：
  1. **无效枚举值处理不一致** —— `priority_id=999` → 422 报错；`status_id=999` / `tracker_id=999` → **201 成功，且静默替换成默认值**，调用方无法感知参数被丢弃。
  2. **无权操作的拒绝方式不统一** —— 无权**改**他人 Issue → **204**（看起来成功，数据未变）；无权**删** → **403** 明确报错。

  → 结论：**接口测试不能只看状态码**。Redmine 的 `204` 不代表改成功，凡 PUT / DELETE 用例都做了「改完再回读」验证。完整清单见 `docs/2.5-测试方案-接口用例设计.md` 第四章。

---

## 七、文档导航

| 你想看什么 | 去哪 |
|---|---|
| 用例本身（交付物） | `test-cases/` —— 界面 69 条、接口 87 条、冒烟 24 条 |
| 用例**怎么设计**出来的 | `docs/2.4`（界面）、`docs/2.5`（接口） |
| 需求 / 接口规格 | `docs/1.2`、`docs/1.3` |
| 执行结果与实测数据 | `docs/2.6-测试报告.md` |
| 环境怎么复现 | `docs/2.2-环境搭建指南.md` + `scripts/` |
| 自动化怎么跑 | `automation/README.md`、`automation/4.2-接口测试执行步骤.md` |
| 日志分析怎么跑 | `log-analysis/README.md` |

---

## 八、说明

- 仓库内的 API Key 和数据库口令是**本机 Docker 测试环境的演示凭证**，只对 `http://localhost:3000` 生效，不涉及任何真实系统；`automation/config.py` 支持用环境变量覆盖。
- 测试账号密码统一为 `Test@1234`。
- **界面语言保持 English**：接口断言里有 18 处直接比对英文名称（`"New"` / `"Bug"` / `"In Progress"` 等），切成中文会集体失败。
