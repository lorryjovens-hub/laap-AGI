# Rust PSI Core 二进制发布路线图

**版本**: v1.0  
**日期**: 2026-07-15  
**状态**: 规划中 / 欢迎社区共建

---

## 1. 目标

为 LAAP 提供一个高性能、可独立部署的 **Rust PSI Core** 原生实现，作为当前 Python fallback 的上位替代：

- **性能**: 认知循环达到 1000-2000 Hz（Python fallback 当前约 10-100 Hz）
- **内存安全**: 通过 Rust 所有权模型消除数据竞争与 UAF
- **部署灵活**: 单二进制文件 + 配置文件即可运行
- **协议兼容**: 通过 CognitiveBus 与 Python 版 LAAP 双向互通

---

## 2. 当前状态

| 组件 | 状态 | 说明 |
|---|---|---|
| Python PSI Core fallback | 可用 | 位于 `psi_core/` 与 `aris_brain/psi_core_bridge.py` |
| Rust PSI Core | 未开始 | 仅完成本路线图与架构设计 |
| FFI / gRPC 桥接 | 未开始 | 计划使用 gRPC + flatbuffers |
| 预编译二进制 | 未发布 | 待 Rust Core 完成 v0.1 后发布 |

当前 LAAP 完全可用，Rust Core 是性能增强项，非阻塞项。

---

## 3. 架构设计

```textn┌─────────────────────────────────────────────────────────┐
│                 LAAP Brain (Python)                      │
│  aris_brain / laap_brain / laap/agi                      │
└──────────────┬──────────────────────────────────────────┘
               │ gRPC / flatbuffers
               ▼
┌─────────────────────────────────────────────────────────┐
│                 Rust PSI Core                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │ Need Engine │  │ Emotion     │  │ Causal Engine   │  │
│  │ (PSI needs) │  │ Dynamics    │  │ (QRE rules)     │  │
│  └─────────────┘  └─────────────┘  └─────────────────┘  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │ World Model │  │ Memory      │  │ Attention       │  │
│  │             │  │ Index       │  │ Scheduler       │  │
│  └─────────────┘  └─────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 4. 里程碑

### Milestone 0: 脚手架与协议定义（2 周）

- [ ] 创建 `rust_core/` 目录与 Cargo workspace
- [ ] 定义 PSI 状态 flatbuffers schema
- [ ] 实现 gRPC 服务桩：`CognitiveBusService`
- [ ] CI 构建：Linux x86_64 / Windows x86_64 / macOS aarch64

### Milestone 1: 核心认知循环（4 周）

- [ ] 实现 `NeedEngine`：curiosity/competence/connectedness 等需求动力学
- [ ] 实现 `EmotionEngine`：valence / arousal / 情感向量更新
- [ ] 实现 `AttentionScheduler`：注意力竞争与选择
- [ ] 与 Python `CognitiveState` 对齐数据格式

### Milestone 2: 记忆与因果引擎（6 周）

- [ ] 实现 `MemoryIndex`：基于 HNSW 的向量 episodic memory
- [ ] 实现 `CausalEngine`：因果规则存储与推理
- [ ] 实现 `WorldModel`：轻量级内部世界模拟
- [ ] 暴露 `/health` 与 `/v1/cognitive_state` HTTP 端点

### Milestone 3: 二进制发布与集成（4 周）

- [ ] GitHub Releases 发布预编译二进制
- [ ] 提供 `laap-psi-core` CLI 单文件运行
- [ ] Python `psi_core_bridge.py` 自动检测并使用 Rust Core
- [ ] 性能基准测试报告

### Milestone 4: 企业级增强（8 周）

- [ ] GPU / NPU 加速推理后端
- [ ] 分布式多实例 Ψ-Net 支持
- [ ] 量化模型与边缘部署

---

## 5. 与 Python 的集成方式

```python
# psi_core_bridge.py 未来检测逻辑
import os

RUST_CORE_BINARY = os.environ.get("LAAP_RUST_PSI_CORE")
if RUST_CORE_BINARY and Path(RUST_CORE_BINARY).exists():
    _core = RustPsiCoreProcess(RUST_CORE_BINARY)
else:
    _core = PythonPsiCoreFallback()
```

---

## 6. 目录规划

```
rust_core/
├── Cargo.toml
├── crates/
│   ├── psi_core/          # 核心库
│   ├── psi_bus/           # gRPC / HTTP 服务
│   ├── psi_memory/        # 记忆索引
│   └── psi_cli/           # 单二进制 CLI
├── schemas/
│   └── cognitive_state.fbs
├── build/
│   └── release.sh
└── README.md
```

---

## 7. 社区参与

欢迎以下形式的贡献：

- 提交 Issue 讨论架构设计
- 认领 Milestone 子任务
- 提供性能基准测试数据
- 赞助 CI runner 用于跨平台构建

---

## 8. 免责声明

Rust PSI Core 目前处于路线图阶段，未提供可运行二进制。LAAP 的 Python 实现已完整可用，可独立满足开发、测试与轻量生产需求。
