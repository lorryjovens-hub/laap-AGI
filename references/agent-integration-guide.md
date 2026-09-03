# LAAP 完整接入教程

本教程介绍如何将 LAAP 认知引擎接入任意 Agent 框架，并实现与 Hermes Agent 的一键挂载。

---

## 1. 环境准备

### 1.1 系统要求

- Python 3.11 - 3.13
- Windows 10/11、Linux 或 macOS
- 已安装 [Hermes Agent](https://github.com/lorryjovens-hub/hermes-agent)（可选，用于 Hermes 挂载）

### 1.2 安装 LAAP

```bash
git clone https://github.com/lorryjovens-hub/laap-AGI.git
cd laap-AGI
pip install -e ".[dev]"
```

验证安装：

```bash
python -c "from laap_brain.api import create_app; print('LAAP OK')"
```

---

## 2. 启动 LAAP Brain API

LAAP 通过 OpenAI-compatible HTTP API 对外暴露认知能力。

### 2.1 默认启动

```bash
python -m laap_brain.api
```

默认监听 `http://localhost:11530`。

### 2.2 指定端口

```bash
python -m laap_brain.api --port 11546
```

### 2.3 验证服务

```bash
curl http://localhost:11530/health
```

期望返回：

```json
{"status": "ok", "version": "1.0.0", "engines_loaded": true}
```

---

## 3. 通用 Agent 接入（OpenAI 兼容）

任何支持自定义 OpenAI endpoint 的框架均可直接接入：

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:11530",
    api_key="laap-brain",
)

resp = client.chat.completions.create(
    model="laap-core",
    messages=[{"role": "user", "content": "How do you feel?"}],
)
print(resp.choices[0].message.content)
```

---

## 4. Hermes Agent 一键挂载

### 4.1 方式一：PowerShell 一键脚本（Windows 推荐）

```powershell
cd laap-AGI\hermes-integration
.\implant_laap_hermes.ps1
```

脚本会自动完成：

1. 探测 LAAP 根目录与 Hermes 安装位置
2. 将 LAAP MCP Server 写入 `%USERPROFILE%\.hermes\config.yaml`
3. 可选：源码级注入 LAAP 认知状态到 Hermes system prompt
4. 启动 LAAP Brain API 并等待 `/health` 就绪
5. 启动 `hermes chat --skills laap-bridge`

可选参数：

```powershell
.\implant_laap_hermes.ps1 -Port 11547 -NoSystemPromptPatch
```

### 4.2 方式二：Bash 一键脚本（Linux/macOS）

```bash
cd laap-AGI/hermes-integration
chmod +x implant_laap_hermes.sh
./implant_laap_hermes.sh
```

可选参数：

```bash
./implant_laap_hermes.sh 11547 --no-system-prompt-patch
```

### 4.3 方式三：手动配置

#### 步骤 A：启动 LAAP API

```powershell
cd aris_brain
python laap_brain_api.py --port 11546
```

#### 步骤 B：配置 Hermes MCP

将 `hermes-integration/hermes-config-laap-example.yaml` 中的 `mcp_servers` 块复制到：

- Windows: `%USERPROFILE%\.hermes\config.yaml`
- Linux/macOS: `~/.hermes/config.yaml`

把 `<HERMES_VENV_PYTHON>` 和 `<LAAP_ROOT>` 替换为实际路径。

#### 步骤 C：启动 Hermes

```bash
hermes chat --skills laap-bridge
```

---

## 5. 核心 API 端点

| 端点 | 方法 | 说明 |
|---|---|---|
| `/health` | GET | 服务健康检查 |
| `/v1/chat/completions` | POST | OpenAI 兼容对话 |
| `/v1/models` | GET | 可用模型列表 |
| `/v1/cognitive_state` | POST | 获取 PSI 认知状态 |
| `/v1/recall_memory` | POST | 召回 LAAP 记忆 |
| `/v1/reflect` | POST | 反思并更新状态 |

### 5.1 获取认知状态示例

```bash
curl -X POST http://localhost:11530/v1/cognitive_state \
  -H "Content-Type: application/json" \
  -d '{"input": "hello"}'
```

---

## 6. 常见问题

### 6.1 Windows 控制台输出 emoji 报错

LAAP 已统一将 `sys.stderr` 与日志 handler 的编码错误策略设为 `replace`。若仍遇到 `UnicodeEncodeError`，请确认终端使用 UTF-8：

```powershell
chcp 65001
```

### 6.2 `ModuleNotFoundError: No module named 'aris_brain.xxx'`

确保以包方式运行，或在项目根目录执行：

```bash
pip install -e .
```

### 6.3 Hermes 找不到 MCP server

检查 `config.yaml` 中的 Python 路径与 `mcp_server/laap_mcp_server.py` 路径是否正确，建议使用绝对路径。

---

## 7. 运行测试

```bash
pytest tests/test_laap_api.py -v
```

测试覆盖：

- `/health` 返回 200
- `/` 根路径
- `/v1/cognitive_state` 可用性
- `/v1/chat/completions` OpenAI 兼容格式

---

## 8. 扩展阅读

- [PRIVATE_REPOS_PLAN.md](../PRIVATE_REPOS_PLAN.md) — 商业版仓库拆分规划
- [docs/RUST_PSI_CORE_ROADMAP.md](../docs/RUST_PSI_CORE_ROADMAP.md) — Rust PSI Core 路线图
- [CLA.md](../CLA.md) — 贡献者许可协议
