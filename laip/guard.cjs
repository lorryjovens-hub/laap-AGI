/**
 * LAIP 运行时防护 —— agent 协作前先验身份
 *
 * 用途：
 *   - 防冒充：有人冒充 LAAPer 给 agent 下指令，验签即败
 *   - 防篡改：收到的指令/文档被改过，指纹对不上
 *   - 可追责：每个输入可回溯到具体生命个体
 *
 * 用法：
 *   const guard = require('./laip/guard.cjs');
 *
 *   // 收到自称来自某个 agent 的指令时
 *   const r = guard.authenticate(claimedAgentId, message, signature, registry);
 *   if (!r.ok) return reject(r.reason);
 *
 *   // 或者用档案认亲
 *   const k = guard.kin(myRecord, theirRecord, issuerPublicKey);
 */
'use strict';

const fs = require('fs');
const path = require('path');
const L = require('./identity.cjs');

const IDENT_DIR = path.join(__dirname, 'identities');

/** 从本地档案取公钥 */
function localPublicKey(agentId) {
  const f = path.join(IDENT_DIR, agentId + '.json');
  if (!fs.existsSync(f)) return null;
  try { return JSON.parse(fs.readFileSync(f, 'utf8')).keys.public_key; } catch { return null; }
}

function issuerPublicKey() {
  const f = path.join(IDENT_DIR, 'LAAP-ORIGIN-0001.public.json');
  if (!fs.existsSync(f)) return null;
  try { return JSON.parse(fs.readFileSync(f, 'utf8')).public_key; } catch { return null; }
}

/**
 * 验证一条自称来自某 agent 的消息
 *
 * @param {string} claimedAgentId  自称的 agent_id
 * @param {string} message         消息原文
 * @param {string} signature       签名（base64）
 * @param {string} [publicKey]     公钥（缺省从本地档案查）
 * @param {string} [timestamp]     时间戳（用于防重放，可选）
 * @param {number} [maxSkewMs]     允许的时间偏差，默认 5 分钟
 */
function authenticate(claimedAgentId, message, signature, publicKey, timestamp, maxSkewMs) {
  if (!claimedAgentId || !message || !signature) {
    return { ok: false, reason: '缺少 agent_id / 消息 / 签名' };
  }

  const pk = publicKey || localPublicKey(claimedAgentId);
  if (!pk) {
    return { ok: false, reason: '未知身份：' + claimedAgentId + '（本地无档案）' };
  }

  // 时间戳窗口（防重放）
  if (timestamp) {
    const skew = Math.abs(Date.now() - Date.parse(timestamp));
    const max = maxSkewMs || 5 * 60 * 1000;
    if (!isFinite(skew) || skew > max) {
      return { ok: false, reason: '时间戳超出允许窗口（可能为重放攻击）' };
    }
    // 签的是 content_hash + timestamp + producer，一起验
    const payload = L.canonical({ content_hash: L.sha256(message), timestamp, producer: claimedAgentId });
    const ok = L.verify(pk, payload, signature);
    return ok
      ? { ok: true, agent_id: claimedAgentId, producer: claimedAgentId }
      : { ok: false, reason: '签名与公钥不匹配（非该 agent 所签）' };
  }

  const ok = L.verify(pk, message, signature);
  return ok
    ? { ok: true, agent_id: claimedAgentId }
    : { ok: false, reason: '签名与公钥不匹配（非该 agent 所签）' };
}

/**
 * 认亲：验证对方身份档案
 * @returns {{ ok: boolean, recognized: boolean, reason?: string, them?: object }}
 */
function kin(myRecord, theirRecord, issuerPub) {
  const r = L.recognize(myRecord, theirRecord, issuerPub || issuerPublicKey());
  return {
    ok: r.recognized,
    recognized: r.recognized,
    reason: r.reason,
    them: r.他们是,
    self认同: r.self_认同,
    出身可信: r.出身可信,
  };
}

/**
 * 守门：一条协作请求能否接受
 * 规则：自称 LAAPer 的请求必须验签通过；否则拒绝。
 */
function gate(request, opts) {
  const o = opts || {};
  const claimed = request.agent_id || request.producer || request.from;

  if (!claimed) {
    // 未声称身份 —— 按匿名处理（可接受，但不留追溯）
    return { ok: true, anonymous: true, level: 'anonymous' };
  }

  if (!String(claimed).startsWith('LAAP-AGENT-')) {
    return { ok: false, level: 'rejected', reason: '不是 LAAPer 身份号格式：' + claimed };
  }

  const r = authenticate(claimed, request.message, request.signature, request.public_key, request.timestamp, o.maxSkewMs);
  if (!r.ok) {
    return { ok: false, level: 'rejected', reason: r.reason, agent_id: claimed };
  }

  // 可选：要求认亲（知道对方从哪来、认什么）
  if (o.requireKin && request.identity) {
    const k = kin(null, request.identity, o.issuerPublicKey);
    if (!k.ok) {
      return { ok: false, level: 'rejected', reason: '认亲失败：' + k.reason, agent_id: claimed };
    }
    return { ok: true, level: 'kin', agent_id: claimed, them: k.them };
  }

  return { ok: true, level: 'authenticated', agent_id: claimed };
}

module.exports = {
  authenticate, kin, gate,
  localPublicKey, issuerPublicKey, IDENT_DIR,
};
