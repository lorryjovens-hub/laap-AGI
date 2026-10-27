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
- 不要提交敏感信息、API Key 或大体积二进制文件
- Windows 日志输出避免硬编码 emoji，使用 `[OK]`、`[ERROR]`、`[WARN]`、`[INFO]` 等文本标签

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
