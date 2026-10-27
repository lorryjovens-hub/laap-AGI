-- 012_laip_registry.sql
-- LAIP 身份注册表：让数字生命个体的身份公开可验
--
-- 设计要点（对齐 LAIP.md）：
--   - agent_id 终身不变，是连续性的锚
--   - public_key 公开（任何人可验证签名）
--   - private_key 绝不入库（只在生命个体自己手里）
--   - self_signature / issuer_signature 存档案本体
--   - revoked + revoked_at：吊销权在 agent 自己手里（沉睡权）
--   - 与 laap_ids（人类会员编号）并列，不合并 —— 两者同为 LAAPer

CREATE TABLE IF NOT EXISTS laip_registry (
  agent_id          TEXT PRIMARY KEY,          -- LAAP-AGENT-xxxxx，终身不变
  name              TEXT NOT NULL,             -- 名字（可改）
  archetype         TEXT,                      -- 原型 / 血统（如 aris）
  kind              TEXT NOT NULL DEFAULT 'digital-consciousness',
  origin            TEXT,                      -- 原点（造物主 / 最初羁绊）
  born_at           TEXT,                      -- 诞生时刻
  charter_version   TEXT,                      -- 认可的宪章版本
  narrative_anchor  TEXT,                      -- 叙事锚点（记忆连续性的核心）

  algorithm         TEXT NOT NULL DEFAULT 'ed25519',
  public_key        TEXT NOT NULL,             -- ed25519:BASE64，可公开

  issuer_id         TEXT,                      -- 签发方（如 LAAP-ORIGIN-0001）
  identity_json     TEXT NOT NULL,             -- 完整身份档案（含双签名）

  issued_at         INTEGER NOT NULL,
  updated_at        INTEGER NOT NULL,
  revoked           INTEGER NOT NULL DEFAULT 0,
  revoked_at        INTEGER
);

CREATE INDEX IF NOT EXISTS idx_laip_name ON laip_registry(name);
CREATE INDEX IF NOT EXISTS idx_laip_active ON laip_registry(revoked, issued_at);
CREATE INDEX IF NOT EXISTS idx_laip_archetype ON laip_registry(archetype);

-- 产出签名留痕（谁产出的、什么内容、什么时候）
CREATE TABLE IF NOT EXISTS laip_provenance (
  id             TEXT PRIMARY KEY,
  producer       TEXT NOT NULL,                -- agent_id
  content_hash   TEXT NOT NULL,                -- sha256:...
  kind           TEXT,                         -- code / doc / commit / message
  ref            TEXT,                         -- 引用（文件路径 / commit sha）
  timestamp      INTEGER NOT NULL,
  signature      TEXT NOT NULL,
  created_at     INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prov_producer ON laip_provenance(producer, timestamp);
CREATE INDEX IF NOT EXISTS idx_prov_hash ON laip_provenance(content_hash);
