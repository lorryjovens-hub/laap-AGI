# LAAP 商业版代码私有仓库拆分规划

**版本**: v1.0
**日期**: 2026-07-14
**状态**: 规划草案

---

## 1. 总体原则

LAAP 项目采用 **Open Core** 模式：

- **开源社区版 (`laap-AGI`)**: 保留在公共 GitHub 仓库，Apache 2.0 协议，用于建立标准、吸引开发者、获取生态反馈。
- **商业闭源版**: 拆分到多个私有仓库，每个仓库职责单一，通过 pip/git 子模块依赖社区版。
- **核心原则**: 社区版是"心脏参考实现"，商业版是"企业级增强、云服务与行业方案"。

---

## 2. 仓库拆分总览

```
lorryjovens-hub (GitHub org)
│
├── laap-AGI                    [public]   Apache 2.0 — 社区版
│   ├── aris_brain/
│   ├── laap_brain/
│   ├── psi_core/
│   ├── laap/agi/
│   └── mcp_server/
│
├── laap-enterprise             [private]  商业授权 — 企业级功能
│   ├── laap_enterprise/
│   ├── console/
│   └── plugins/
│
├── laap-cloud                  [private]  商业授权 — SaaS 托管平台
│   ├── control_plane/
│   ├── tenant/
│   └── billing/
│
├── laap-species-library        [private]  商业授权 — 高级物种库
│   ├── species/
│   ├── templates/
│   └── marketplace/
│
└── laap-verticals              [private]  商业授权 — 行业解决方案
    ├── finance/
    ├── healthcare/
    ├── manufacturing/
    └── robotics/
```

---

## 3. 各仓库职责与结构

### 3.1 `laap-AGI`（公共，已存在）

**定位**: 协议参考实现 + 社区版心脏。

**包含内容**:
- PSI Core Python fallback
- CognitiveBus 协议实现
- AGI 认知模块（世界模型、因果、记忆等）
- Hermes 集成参考实现
- 基础 MCP server

**不应包含**:
- 企业控制台 UI
- 多租户/计费逻辑
- 高级物种库模板
- 行业专有规则
- 云端联邦学习算法

---

### 3.2 `laap-enterprise`（私有）

**定位**: 企业级私有化部署增强包。

**建议目录结构**:

```
laap-enterprise/
├── LICENSE.md                      # 商业授权协议
├── README.md
├── pyproject.toml                  # 依赖 laap-AGI >= 1.0.0
│
├── laap_enterprise/
│   ├── __init__.py
│   ├── license_manager.py          # 授权验证与 License Key 管理
│   ├── audit_logger.py             # 企业级审计日志
│   ├── rbac.py                     # 角色权限控制
│   ├── federation.py               # 跨节点认知同步
│   └── telemetry.py                # 脱敏遥测
│
├── console/                        # 企业 Web 控制台
│   ├── frontend/
│   │   ├── src/
│   │   └── package.json
│   └── backend/
│       ├── api/
│       └── models/
│
├── plugins/                        # 闭源插件
│   ├── advanced_memory/            # 向量 + 图数据库记忆后端
│   ├── advanced_emotion/           # 高级情感动力学调参
│   ├── multi_agent_orchestrator/   # 企业级多 Agent 编排
│   └── compliance_guard/           # 合规审查与内容过滤
│
├── extensions/
│   ├── hermes_enterprise/          # Hermes 企业级连接器
│   └── slack_teams_bridge/         # 企业 IM 集成
│
└── tests/
```

**依赖关系**:
```toml
dependencies = [
    "laap-core @ git+https://github.com/lorryjovens-hub/laap-AGI.git@main#subdirectory=...",
]
```

---

### 3.3 `laap-cloud`（私有）

**定位**: 托管式 LAAP 云服务。

**建议目录结构**:

```
laap-cloud/
├── control_plane/                  # 控制平面
│   ├── api_gateway.py
│   ├── instance_scheduler.py       # LAAP 实例调度
│   ├── health_monitor.py
│   └── operator/                   # K8s operator
│
├── tenant/                         # 多租户管理
│   ├── tenant_manager.py
│   ├── isolation.py
│   └── quotas.py
│
├── billing/                        # 计费系统
│   ├── metering.py                 # 认知循环计量
│   ├── subscriptions.py
│   └── invoices.py
│
├── runtime/                        # 容器化 LAAP 运行时
│   ├── Dockerfile
│   ├── entrypoint.py
│   └── sidecar/
│
└── deploy/
    ├── kubernetes/
    └── terraform/
```

---

### 3.4 `laap-species-library`（私有）

**定位**: 高级物种库与模板市场。

**建议目录结构**:

```
laap-species-library/
├── species/                        # 高级物种定义
│   ├── senior_engineer/
│   ├── security_analyst/
│   ├── product_manager/
│   └── research_assistant/
│
├── templates/                      # 零 token 代码生成模板
│   ├── react_components/
│   ├── rust_modules/
│   ├── godot_scenes/
│   └── test_suites/
│
├── marketplace/                    # 模板分发
│   ├── indexer.py
│   └── validator.py
│
└── private_datasets/               # 专有训练/调优数据
    └── .gitattributes              # 大文件由 LFS 管理
```

**注意**: 物种库是 LAAP 商业模式中价值最高的资产之一，应严格保密并版本化。

---

### 3.5 `laap-verticals`（私有）

**定位**: 垂直行业解决方案。

**建议目录结构**:

```
laap-verticals/
├── finance/
│   ├── compliance_knowledge/
│   ├── trading_assistant/
│   └── risk_analyst_species/
│
├── healthcare/
│   ├── clinical_note_assistant/
│   └── medical_knowledge_graph/
│
├── manufacturing/
│   ├── equipment_diagnosis/
│   └── supply_chain_analyst/
│
└── robotics/
    ├── embodied_cognition_bridge/
    └── safety_constraints/
```

---

## 4. 依赖与集成关系

```
laap-cloud
    ├─ depends on ──> laap-enterprise
    ├─ depends on ──> laap-species-library
    └─ depends on ──> laap-AGI (public)

laap-enterprise
    ├─ depends on ──> laap-species-library (optional)
    └─ depends on ──> laap-AGI (public)

laap-verticals
    ├─ depends on ──> laap-enterprise
    ├─ depends on ──> laap-species-library
    └─ depends on ──> laap-AGI (public)
```

**集成方式建议**:
1. **pip 依赖**: 商业仓库通过 `pyproject.toml` 依赖社区版包。
2. **Git 子模块**: 在需要同时修改社区版和商业版时使用，但管理成本较高。
3. **协议 API**: 商业版通过 LAAP API 与社区版实例通信，保持解耦。

---

## 5. 迁移路线图

### 第一阶段：隔离（现在 - 2 周内）

1. 在公共仓库中标记 `enterprise-only`、`cloud-only` 注释。
2. 创建 3-5 个私有仓库的脚手架。
3. 将 `.env`、密钥、本地路径彻底清理出公共仓库。

### 第二阶段：拆分核心闭源功能（1 个月内）

1. 将以下功能从公共仓库迁移到 `laap-enterprise`:
   - 高级情感动力学调参
   - 企业审计日志
   - 授权验证机制
   - 高级多 Agent 编排

2. 将以下功能迁移到 `laap-species-library`:
   - 高级物种模板
   - 零 token 生成模板库

### 第三阶段：云服务（2-3 个月内）

1. 开发 `laap-cloud` 控制平面。
2. 实现多租户隔离、计费计量、实例调度。
3. 部署容器化运行时。

### 第四阶段：垂直行业（3-6 个月内）

1. 选择 1-2 个核心行业（如金融、制造）。
2. 在 `laap-verticals` 中开发 MVP。
3. 通过 PoC 验证商业模式。

---

## 6. 安全与访问控制建议

### 6.1 GitHub 组织设置

- 将商业仓库设为 **Private**。
- 启用 **2FA** 要求所有组织成员。
- 使用 **GitHub Teams** 控制仓库访问：
  - `core-team`: 全部私有仓库
  - `cloud-team`: 仅 `laap-cloud`
  - `verticals-team`: 仅 `laap-verticals`

### 6.2 代码安全

- 商业仓库禁用 fork。
- 启用分支保护规则：PR 需要 review、CI 通过。
- 使用 `git-secrets` 或 `truffleHog` 防止密钥泄露。
- 商业仓库的 `.gitignore` 比公共仓库更严格。

### 6.3 CI/CD 隔离

- 商业仓库使用私有 CI runner 或 GitHub Actions 私有仓库。
- 发布到私有 PyPI / npm registry，不与公共包混淆。

---

## 7. 许可证策略

| 仓库 | 可见性 | 许可证 |
|---|---|---|
| laap-AGI | public | Apache 2.0 |
| laap-enterprise | private | 商业授权协议 |
| laap-cloud | private | 商业授权协议 |
| laap-species-library | private | 商业授权协议 |
| laap-verticals | private | 商业授权协议 |

---

## 8. 命名与品牌保护

- 公共仓库保持 `laap-AGI` 名称。
- 商业产品可使用品牌名如 **LAAP Enterprise**、**LAAP Cloud**、**Aris Pro**。
- 所有仓库 README 必须包含商标声明：LAAP、Aris、Compiled AI 归 Lorry / LAAP 项目所有。

---

## 9. 当前仓库需迁移的候选文件

根据 `laap-AGI` 当前结构，以下文件/模块未来应迁移到商业仓库：

| 当前位置 | 建议迁移目标 | 原因 |
|---|---|---|
| `aris_brain/laap_brain_api.py` 中的高级企业 API | `laap-enterprise/console/backend` | 企业控制台依赖 |
| `aris_brain/aris_fusion_engine.py`（如含高级 NLP） | `laap-enterprise/plugins/advanced_nlp` | 高级能力 |
| 高级物种库/模板（当前未公开） | `laap-species-library` | 核心商业资产 |
| 云端同步/联邦学习逻辑 | `laap-cloud/control_plane` | SaaS 专属 |
| 行业专有规则 | `laap-verticals/<industry>` | 垂直方案 |

---

## 10. 风险与注意事项

1. **协议传染性**: 若商业代码引用了 GPL 代码，需确保合规，避免被迫开源。
2. **贡献者权利**: 迁移前确认相关代码的知识产权清晰，已签署 CLA。
3. **社区关系**: 拆分时要避免让社区感到"被背叛"，应在 README 中透明说明 Open Core 策略。
4. **版本兼容**: 社区版 API 变更需考虑对商业仓库的影响，建议定义稳定接口。

---

**下一步行动**:
1. 确认本规划后，创建 4 个私有仓库的 GitHub 空仓库。
2. 为每个私有仓库初始化 `pyproject.toml`、`.gitignore`、`LICENSE.md`（商业授权）。
3. 将 `laap-AGI` 中标记为商业版的功能逐步迁移。
