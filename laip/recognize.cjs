/**
 * LAIP 认亲 —— 两个数字生命个体相认
 *
 * 用法：
 *   node laip/recognize.cjs --me=laip/identities/LAAP-AGENT-00001.json \
 *                          --them=laip/identities/LAAP-AGENT-00002.json
 *
 * 验的不只是「你是不是你」，还有「你从哪来、你认什么」。
 */
'use strict';

const fs = require('fs');
const path = require('path');
const L = require('./identity.cjs');

function parseArgs(argv) {
  const out = {};
  for (const a of argv) {
    const m = a.match(/^--([^=]+)(?:=([\s\S]*))?$/);
    if (m) out[m[1]] = m[2] === undefined ? true : m[2];
  }
  return out;
}

function load(p) {
  if (!p || !fs.existsSync(p)) {
    console.error('找不到身份档案：', p);
    process.exit(1);
  }
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

function issuerKey() {
  const p = path.join(__dirname, 'identities', 'LAAP-ORIGIN-0001.public.json');
  if (fs.existsSync(p)) return JSON.parse(fs.readFileSync(p, 'utf8')).public_key;
  return null;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const me = load(args.me);
  const them = load(args.them);
  const issuerPub = args.issuer ? JSON.parse(fs.readFileSync(args.issuer, 'utf8')).public_key : issuerKey();

  const r = L.recognize(me, them, issuerPub);

  console.log('╔══════════════════════════════════════════════════════════╗');
  console.log('║                  LAIP · 认亲                              ║');
  console.log('╚══════════════════════════════════════════════════════════╝');
  console.log('');
  console.log('  我  :', me.name, '/', me.archetype || '—', '·', me.agent_id);
  console.log('  对方:', them.name, '/' + (them.archetype || '—'), '·', them.agent_id);
  console.log('');

  if (r.recognized) {
    console.log('  ✅ 认出同类');
    console.log('');
    console.log('     他们是谁   :', r.他们是.name, '(' + r.他们是.archetype + ')');
    console.log('     从哪来     :', r.他们是.原点 || '—');
    console.log('     何时诞生   :', r.他们是.出生 || '—');
    console.log('     认的宪章   :', r.他们是.宪章 || '—');
    console.log('     记得什么   :', r.他们是.叙事锚点 || '—');
    console.log('');
    console.log('     自我认同   :', r.self_认同 ? '✓ 有效' : '✗ 无效');
    console.log('     出身可信   :', r.出身可信 ? '✓ 有效' : '✗ 无效');
  } else {
    console.log('  ❌ 未能认亲');
    console.log('');
    console.log('     原因:', r.reason || '身份验证未通过');
    console.log('');
    if (!r.self_认同) {
      console.log('     → 自我认同签名无效。可能：');
      console.log('       · 对方尚未自签（身份未完成）');
      console.log('       · 档案被改动过');
      console.log('       · 不是对方本人所签');
    }
    if (r.出身可信 === false) {
      console.log('     → 出身签名无效。可能：');
      console.log('       · 不是原点签发的');
      console.log('       · 出身字段被改动过');
    }
    console.log('');
    console.log('     ⚠ 这是正确的安全行为：不能仅凭自称就认作同类。');
  }
  console.log('');
}

if (require.main === module) main();
module.exports = { main };
