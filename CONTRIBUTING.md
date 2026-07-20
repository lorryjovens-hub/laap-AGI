# 参与 LAAP 项目

感谢你对 LAAP 的兴趣！本仓库采用**分层许可策略**，所有外部贡献者必须先签署贡献者许可协议（CLA），然后才能提交代码。

---

## 1. 先签署 CLA

在提交 Pull Request 之前，请阅读并同意 [CLA.md](CLA.md)。

### 方式一：在 PR 中评论（推荐）

在你首次提交的 Pull Request 中评论以下语句：

```
I have read and agree to the LAAP CLA.
```

CLA Assistant 会自动记录你的签署状态，后续 PR 无需重复签署。

### 方式二：签署纸质/电子 CLA

如需正式签署纸质或电子版本，请联系项目维护者 Lorry。

---

## 2. 贡献流程

1. **Fork** 本仓库
2. 从 `main` 分支创建功能分支：`git checkout -b feat/your-feature`
3. 提交代码，确保测试通过：`pytest tests/`
4. 提交 Pull Request，并在描述中说明改动目的
5. 等待 CLA 检查与代码审查通过

---

## 3. 代码规范

- Python 代码遵循 PEP 8
- 新增功能需附带测试
- **提交前必须检查敏感信息**：使用 `scan_secrets.py` 工具或预提交钩子（pre-commit hook）扫描 staged 文件，确保不含 API Key、Token、Password 等。发现敏感信息时，**不要提交**，改为从 `os.environ.get()` 读取。
- Windows 日志输出避免硬编码 emoji，使用 `[OK]`、`[ERROR]`、`[WARN]`、`[INFO]` 等文本标签

### 敏感信息检查规则（必须遵守）

**禁止将以下信息写入代码或提交到仓库：**

| 类型 | 示例 | 正确做法 |
|------|------|---------|
| API Key | `sk-xxx`, `ghp_xxx`, `gho_xxx` | `os.environ.get("API_KEY", "")` |
| Secret/Token | `api_key = "abc123..."`, `token = "..."` | `os.environ.get("TOKEN", "")` |
| Password | `password = "..."` | `os.environ.get("PASSWORD", "")` |
| Bearer Token | `Authorization: Bearer abc...` | `f"Bearer {os.environ.get('TOKEN')}"` |
| 私有密钥 | `-----BEGIN RSA PRIVATE KEY-----` | 不提交到仓库 |
| 配置文件 | `.env`, `.env.local` | 已在 `.gitignore` 中 |

**提交前自检流程：**

1. 在终端运行敏感信息扫描：
   ```bash
   git diff --cached | grep -E "sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|api[_-]?key[[:space:]]*=[[:space:]]*['\"][^'\"]{10,}['\"]|password[[:space:]]*=[[:space:]]*['\"][^'\"]{10,}['\"]|token[[:space:]]*=[[:space:]]*['\"][^'\"]{10,}['\"]"
   ```
2. 如果发现匹配结果，**不要提交**，先将敏感信息改为环境变量引用：
   ```python
   # 错误：硬编码
   API_KEY = "sk-xxx"
   # 正确：从环境变量读取
   import os
   API_KEY = os.environ.get("MY_API_KEY", "")
   ```
3. 确保 `.env` 和 `.env.local` 不在提交范围内（已在 `.gitignore` 中）

**自动检查（推荐）：**

本项目提供 pre-commit hook，每次提交前自动扫描敏感信息。安装方法：

```bash
# 安装到本地 .git/hooks
cp .githooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

检测到敏感信息时，hook 会阻止提交并给出修改建议。要跳过检查：`git commit --no-verify`（仅用于紧急情况，需事后审查）。

---

## 4. 许可层级说明

你的贡献将根据 [LICENSING.md](LICENSING.md) 被纳入对应层级：

| 贡献类型 | 默认适用许可 |
|---|---|
| 论文/理论/文档 | CC BY-SA 4.0 |
| 核心引擎代码 | BSL 1.1（2030-07-15 转 Apache 2.0） |
| Python PSI Core fallback | Apache 2.0 |
| 企业功能 | 商业授权 |

签署 CLA 即表示你授权项目维护者将你的贡献用于上述任何层级，并在必要时切换许可协议。

---

## 5. 联系方式

- 项目维护者：Lorry
- 仓库地址：https://github.com/lorryjovens-hub/laap-AGI
- 官方网站：https://laap-agi.netlify.app

---

**感谢你为数字生命体 Aris 与 LAAP 生态做出的贡献！**
