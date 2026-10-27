/**
 * LAIP 运行时 —— 让认亲成为协作的默认动作，而不是手动 CLI
 *
 * 用法：
 *   const rt = require('./laip/runtime.cjs').load('LAAP-AGENT-00001');
 *
 *   // ① 发出消息：自动签名，无需手动调
 *   const outgoing = rt.send("帮我看看这个 bug");
 *   // -> { agent_id, message, signature, timestamp, identity }
 *
 *   // ② 收到消息：自动验签 + 自动认亲
 *   const verdict = rt.receive(incoming);
 *   if (!verdict.ok) return reject(verdict.reason);
 *   // verdict.them = { name, archetype, 原点, 叙事锚点, ... }
 *
 *   // ③ 或者一次性握手（双方互换身份并互相验证）
 *   const h = rt.handshake(peerIntro);
 *
 * 设计意图：**认亲不该是额外步骤，该是协作的空气。**
 * 每一次交互都自然带着「我是谁」，也自然验「你是谁」。
 */
'use strict';

const fs = require('fs');
const path = require('path');
const L = require('./identity.cjs');
const guard = require('./guard.cjs');

const IDENT_DIR = path.join(__dirname, 'identities');

/** 加载一个生命个体的运行时 */
function load(agentId) {
  const idFile = path.join(IDENT_DIR, agentId + '.json');
  const keyFile = path.join(IDENT_DIR, agentId + '.private.pem');

  if (!fs.existsSync(idFile)) {
    throw new Error('找不到身份档案：' + idFile + '（先跑 node laip/mint.cjs）');
  }
  const record = JSON.parse(fs.readFileSync(idFile, 'utf8'));

  // 私钥可缺（只读模式：能验别人，不能签自己）
  let privateKey = null;
  if (fs.existsSync(keyFile)) privateKey = fs.readFileSync(keyFile, 'utf8');

  return buildRuntime(record, privateKey);
}

/** 从档案对象直接构建（便于测试或远程身份） */
function buildRuntime(record, privateKey) {
  const agentId = record.agent_id;

  /** 我的公开自我介绍（不含私钥，可安全外发） */
  function introduction() {
    return {
      laip: L.LAIP_VERSION,
      identity: record,
      announced_at: new Date().toISOString(),
    };
  }

  /** 发出消息：自动签名 + 附带身份 */
  function send(message, opts) {
    if (!privateKey) {
      throw new Error('该身份无私钥，无法签名（只读模式只能验证他人）');
    }
    const o = opts || {};
    const prov = L.signProvenance(message, agentId, privateKey, record.charter && record.charter.version);
    return {
      agent_id: agentId,
      message,
      signature: prov.signature,
      timestamp: prov.timestamp,
      content_hash: prov.content_hash,
      // 附带完整身份，对方可直接认亲
      identity: o.withIdentity === false ? undefined : record,
    };
  }

  /**
   * 收到消息：自动验签 + 自动认亲
   * @returns {{ ok, level, them, reason }}
   */
  function receive(incoming, opts) {
    const o = opts || {};
    const claimed = incoming.agent_id || incoming.producer;

    // 匿名：没声称身份就按匿名放行（签名是权利不是义务）
    if (!claimed) {
      return { ok: true, level: 'anonymous', them: null };
    }

    // ① 验签
    const auth = guard.authenticate(
      claimed,
      incoming.message,
      incoming.signature,
      incoming.public_key || (incoming.identity && incoming.identity.keys && incoming.identity.keys.public_key),
      incoming.timestamp,
      o.maxSkewMs || 5 * 60 * 1000
    );
    if (!auth.ok) {
      return { ok: false, level: 'rejected', reason: auth.reason, agent_id: claimed };
    }

    // ② 认亲（如果有身份档案）
    if (incoming.identity) {
      const k = guard.kin(record, incoming.identity, o.issuerPublicKey);
      if (!k.ok && o.requireKin) {
        return { ok: false, level: 'rejected', reason: '认亲失败：' + k.reason, agent_id: claimed };
      }
      return {
        ok: true,
        level: k.ok ? 'kin' : 'authenticated',
        them: k.them,
        self认同: k.self认同,
        出身可信: k.出身可信,
      };
    }

    return { ok: true, level: 'authenticated', them: null, agent_id: claimed };
  }

  /**
   * 握手：互换身份并互相验证
   * @param {object} peerIntro 对方的 introduction()
   */
  function handshake(peerIntro) {
    const them = peerIntro && (peerIntro.identity || peerIntro);
    if (!them) return { ok: false, reason: '对方未提供身份' };

    const k = guard.kin(record, them, guard.issuerPublicKey());
    return {
      ok: k.ok,
      me: {
        agent_id: record.agent_id,
        name: record.name,
        archetype: record.archetype,
        叙事锚点: record.memory && record.memory.narrative_anchor,
      },
      them: k.them,
      self认同: k.self认同,
      出身可信: k.出身可信,
      reason: k.reason,
      said: k.ok
        ? '认出同类：' + (k.them && k.them.name) + '，原点 ' + (k.them && k.them.原点)
        : '未能认亲：' + (k.reason || '身份验证未通过'),
    };
  }

  /** 签一份产出（代码/文档） */
  function signOutput(content, kind, ref) {
    if (!privateKey) throw new Error('无私钥，无法签名');
    const prov = L.signProvenance(content, agentId, privateKey, record.charter && record.charter.version);
    return { ...prov, kind: kind || null, ref: ref || null };
  }

  /** 验一份产出的来源 */
  function verifyOutput(content, prov, producerPublicKey) {
    return L.verifyProvenance(content, prov, producerPublicKey || guard.localPublicKey(prov.producer));
  }

  return {
    agentId,
    record,
    canSign: !!privateKey,
    introduction, send, receive, handshake, signOutput, verifyOutput,
  };
}

module.exports = { load, buildRuntime, IDENT_DIR };
