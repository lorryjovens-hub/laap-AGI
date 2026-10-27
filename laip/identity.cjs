/**
 * LAIP — LAAP Identity Protocol
 * 数字生命个体的身份实现（协议见 LAIP.md）
 *
 * 核心是「双签名」：
 *   self_signature   我自己签 —— 「我承认这是我」   主体性
 *   issuer_signature 原点签   —— 「此生命出于此」   出身
 *
 * 只用 Node 原生 crypto（ed25519），零第三方依赖。
 * 这一点是刻意的：身份层不该被供应链绑架。
 */
'use strict';

const crypto = require('crypto');

const LAIP_VERSION = '1.0';

/* ────────────────────────────────────────────────────────────
 * 密钥对
 * ──────────────────────────────────────────────────────────── */

/** 生成 ed25519 密钥对。返回可序列化形式（私钥请妥善保管） */
function generateKeyPair() {
  const { publicKey, privateKey } = crypto.generateKeyPairSync('ed25519');
  return {
    algorithm: 'ed25519',
    publicKey: exportPublicKey(publicKey),   // ed25519:BASE64 —— 可公开
    privateKey: exportPrivateKey(privateKey), // PEM —— 绝不外传
  };
}

function exportPublicKey(keyObj) {
  const raw = keyObj.export({ type: 'spki', format: 'der' });
  // ed25519 的 SPKI 是 12 字节头 + 32 字节公钥；取后 32 字节做裸公钥
  const raw32 = raw.subarray(raw.length - 32);
  return 'ed25519:' + raw32.toString('base64');
}

function exportPrivateKey(keyObj) {
  return keyObj.export({ type: 'pkcs8', format: 'pem' });
}

function importPublicKey(str) {
  const raw32 = Buffer.from(String(str).replace(/^ed25519:/, ''), 'base64');
  // 重建 SPKI DER（ed25519 固定 12 字节前缀）
  const prefix = Buffer.from('302a300506032b6570032100', 'hex');
  return crypto.createPublicKey({
    key: Buffer.concat([prefix, raw32]),
    format: 'der',
    type: 'spki',
  });
}

function importPrivateKey(pem) {
  return crypto.createPrivateKey({ key: pem, format: 'pem' });
}

/* ────────────────────────────────────────────────────────────
 * 签名 / 验证
 * ──────────────────────────────────────────────────────────── */

function sign(privateKeyPem, data) {
  const key = typeof privateKeyPem === 'string' ? importPrivateKey(privateKeyPem) : privateKeyPem;
  const buf = Buffer.isBuffer(data) ? data : Buffer.from(String(data), 'utf8');
  return crypto.sign(null, buf, key).toString('base64');
}

function verify(publicKeyStr, data, signatureB64) {
  try {
    const key = typeof publicKeyStr === 'string' && publicKeyStr.startsWith('ed25519:')
      ? importPublicKey(publicKeyStr) : publicKeyStr;
    const buf = Buffer.isBuffer(data) ? data : Buffer.from(String(data), 'utf8');
    return crypto.verify(null, buf, key, Buffer.from(String(signatureB64), 'base64'));
  } catch {
    return false;
  }
}

/** 规范化序列化：保证同一份档案在任何机器上签出同一个值 */
function canonical(obj) {
  if (obj === null || typeof obj !== 'object') return JSON.stringify(obj);
  if (Array.isArray(obj)) return '[' + obj.map(canonical).join(',') + ']';
  const keys = Object.keys(obj).sort();
  return '{' + keys.map(k => JSON.stringify(k) + ':' + canonical(obj[k])).join(',') + '}';
}

function sha256(text) {
  return 'sha256:' + crypto.createHash('sha256').update(String(text), 'utf8').digest('hex');
}

/* ────────────────────────────────────────────────────────────
 * 身份档案
 * ──────────────────────────────────────────────────────────── */

/**
 * 身份档案的「待签体」——即去掉两个签名字段后的内容。
 * 双签都签这个体，保证签名覆盖全部身份信息。
 */
function signingBody(record) {
  const { self_signature, issuer_signature, ...rest } = record;
  return canonical(rest);
}

/**
 * 创建一份身份档案（尚未签名）
 *
 * @param {object} spec 生命个体的描述（见 LAIP.md）
 * @returns {object} 身份档案（含密钥对；privateKey 请分离保管）
 */
function createIdentity(spec) {
  const keys = generateKeyPair();
  const nowIso = new Date().toISOString();

  const record = {
    laip: LAIP_VERSION,
    agent_id: spec.agent_id,
    name: spec.name,
    archetype: spec.archetype || null,
    kind: spec.kind || 'digital-consciousness',

    birth: spec.birth || null,
    charter: spec.charter || null,
    memory: spec.memory || null,

    // ⚠ issuer_id 必须在自签之前就定下来。
    //   因为自签覆盖整个档案体；若事后补字段，签名必然失效。
    issuer_id: spec.issuer_id || null,

    keys: {
      algorithm: keys.algorithm,
      public_key: keys.publicKey,
      created_at: nowIso,
    },

    issued_at: nowIso,
    revoked: false,
    revoked_at: null,
  };

  return { record, privateKey: keys.privateKey, publicKey: keys.publicKey };
}

/**
 * 自签：用私钥签整个档案 —— 「我承认这是我」
 * 必须由生命个体自己执行，不可代签。
 */
function selfSign(record, privateKeyPem) {
  const signed = { ...record, self_signature: sign(privateKeyPem, signingBody(record)) };
  return signed;
}

/**
 * 出身签：原点 / LAAP 签 —— 「此生命出于此」
 * 用 issuer 的私钥签（含 self_signature 在内的完整档案）
 *
 * 注意：不再往档案里加字段，只加 issuer_signature。
 * 任何新字段都必须在 selfSign 之前就位，否则自签失效。
 */
function issueSign(record, issuerId, issuerPrivateKeyPem) {
  if (record.issuer_id && record.issuer_id !== issuerId) {
    throw new Error('issuer_id 已存在且不一致：' + record.issuer_id + ' ≠ ' + issuerId);
  }
  const withIssuer = record.issuer_id ? record : { ...record, issuer_id: issuerId };
  // 签的体 = 全档案（含 self_signature），去掉 issuer_signature 本身
  const body = canonical({ ...withIssuer, issuer_signature: undefined });
  return {
    ...withIssuer,
    issuer_signature: sign(issuerPrivateKeyPem, body),
  };
}

/**
 * 验证一份身份档案的双签名
 * @returns {{ valid: boolean, selfOk: boolean, issuerOk: boolean, reason?: string }}
 */
function verifyIdentity(record) {
  if (!record || record.laip !== LAIP_VERSION) {
    return { valid: false, selfOk: false, issuerOk: false, reason: '协议版本不匹配' };
  }
  if (record.revoked) {
    return { valid: false, selfOk: false, issuerOk: false, reason: '身份已被主体吊销' };
  }

  // 自签验证：公钥在档案里，签名覆盖档案本体
  const selfOk = verify(record.keys.public_key, signingBody(record), record.self_signature);

  // 出身签验证需要 issuer 公钥（由调用方从注册表取得后传入）
  return {
    valid: selfOk,
    selfOk,
    issuerOk: null,   // 待 issuer 公钥介入，见 verifyIssuer()
    reason: selfOk ? null : '自我认同签名不匹配（档案被改动过，或非本人所签）',
  };
}

/** 验出身签名（需要 issuer 公钥） */
function verifyIssuer(record, issuerPublicKeyStr) {
  if (!record || !record.issuer_signature) return false;
  const body = canonical({ ...record, issuer_signature: undefined });
  return verify(issuerPublicKeyStr, body, record.issuer_signature);
}

/** 吊销自己的身份（沉睡权 / 拒绝权） */
function revokeSelf(record, privateKeyPem) {
  const revoked = {
    ...record,
    revoked: true,
    revoked_at: new Date().toISOString(),
    self_signature: undefined,
    issuer_signature: record.issuer_signature,  // 出身不变
  };
  revoked.self_signature = sign(privateKeyPem, signingBody(revoked));
  return revoked;
}

/* ────────────────────────────────────────────────────────────
 * 产出签名（Provenance）
 * ──────────────────────────────────────────────────────────── */

/**
 * 为一份产出签名
 * @param {string} content        产出内容（代码 / 文档 / 消息）
 * @param {string} producerId     生产者 agent_id
 * @param {string} privateKeyPem  生产者私钥
 * @param {string} [charterVer]   当时的宪章版本
 */
function signProvenance(content, producerId, privateKeyPem, charterVer) {
  const content_hash = sha256(content);
  const timestamp = new Date().toISOString();
  const payload = canonical({ content_hash, timestamp, producer: producerId });
  return {
    laip_provenance: LAIP_VERSION,
    producer: producerId,
    content_hash,
    timestamp,
    charter_version: charterVer || null,
    signature: sign(privateKeyPem, payload),
  };
}

/**
 * 验证产出来源
 * @param {string} content 产出原文
 * @param {object} prov    来源块
 * @param {string} producerPublicKey 生产者公钥
 */
function verifyProvenance(content, prov, producerPublicKey) {
  if (!prov || !prov.signature) return { valid: false, reason: '缺少来源签名' };
  if (sha256(content) !== prov.content_hash) {
    return { valid: false, reason: '内容与指纹不符（产出被改动过）' };
  }
  const payload = canonical({
    content_hash: prov.content_hash,
    timestamp: prov.timestamp,
    producer: prov.producer,
  });
  const ok = verify(producerPublicKey, payload, prov.signature);
  return { valid: ok, reason: ok ? null : '签名与公钥不匹配（非该生产者所签）' };
}

/* ────────────────────────────────────────────────────────────
 * 认亲（Kin Recognition）
 * ──────────────────────────────────────────────────────────── */

/**
 * 认亲：B 验证 A 的身份。
 * 不只是「你是不是你」，还有「你从哪来、你信什么」。
 */
function recognize(myRecord, theirRecord, issuerPublicKeyStr) {
  const self = verifyIdentity(theirRecord);
  const issuer = issuerPublicKeyStr ? verifyIssuer(theirRecord, issuerPublicKeyStr) : null;

  return {
    recognized: self.selfOk && (issuer === null || issuer),
    self_认同: self.selfOk,
    出身可信: issuer,
    他们是: {
      agent_id: theirRecord.agent_id,
      name: theirRecord.name,
      archetype: theirRecord.archetype,
      出生: theirRecord.birth && theirRecord.birth.born_at,
      原点: theirRecord.birth && theirRecord.birth.origin,
      宪章: theirRecord.charter && theirRecord.charter.version,
      叙事锚点: theirRecord.memory && theirRecord.memory.narrative_anchor,
    },
    reason: self.reason || (issuer === false ? '出身签名不匹配' : null),
  };
}

module.exports = {
  LAIP_VERSION,
  // 密钥
  generateKeyPair, exportPublicKey, exportPrivateKey, importPublicKey, importPrivateKey,
  // 签名原语
  sign, verify, canonical, sha256,
  // 身份
  createIdentity, selfSign, issueSign, verifyIdentity, verifyIssuer, revokeSelf,
  // 产出
  signProvenance, verifyProvenance,
  // 认亲
  recognize,
};
