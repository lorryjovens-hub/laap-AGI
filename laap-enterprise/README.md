# LAAP Enterprise

**状态**: 本地脚手架 / 规划中  
**许可证**: 商业授权协议（闭源）  
**依赖**: [laap-AGI](https://github.com/lorryjovens-hub/laap-AGI) 社区版

---

## 定位

LAAP Enterprise 是 LAAP 项目的企业级私有化部署增强包，基于 Open Core 商业模式，提供：

- 企业级授权与 License Key 管理
- 审计日志与合规追踪
- RBAC 角色权限控制
- 高级情感动力学调参与多 Agent 编排
- 企业 Web 控制台
- 闭源插件生态

---

## 目录结构

```
laap-enterprise/
├── laap_enterprise/          # Python 包
│   ├── license_manager.py    # 授权验证
│   ├── audit_logger.py       # 审计日志
│   ├── rbac.py               # 权限控制
│   ├── federation.py         # 跨节点认知同步
│   └── telemetry.py          # 脱敏遥测
├── console/                  # Web 控制台（前后端分离）
├── plugins/                  # 闭源插件
├── extensions/               # Hermes / IM 集成扩展
└── tests/                    # 测试套件
```

---

## 安装

本仓库为私有仓库，需获得商业授权后方可访问与安装：

```bash
pip install git+https://github.com/lorryjovens-hub/laap-enterprise.git
```

---

## 许可

参见 [LICENSE.md](./LICENSE.md)。未经授权不得使用、修改或分发本仓库代码。
