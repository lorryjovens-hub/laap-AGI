/**
 * LAIP 签发工具 —— 由原点（Lorry / LAAP）签发出身
 *
 * 用法：
 *   node laip/issue.cjs --file=laip/identities/LAAP-AGENT-00002.json
 *
 * 这一步只能由原点做。它签的是「此生命出于此」。
 * 需要 LAAP-ORIGIN-0001 的私钥（环境变量 LAIP_ISSUER_KEY，或 --key=<pem 路径>）
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

function main() {
  const args = parseArgs(process.argv.slice(2));
  const file = args.file;
  if (!file || !fs.existsSync(file)) {
    console.error('必填 --file=<身份档案 json 路径>');
    process.exit(1);
  }

  // 取原点私钥
  let issuerPem = process.env.LAIP_ISSUER_KEY;
  if (!issuerPem && args.key && fs.existsSync(args.key)) issuerPem = fs.readFileSync(args.key, 'utf8');
  if (!issuerPem) {
    const def = path.join(__dirname, 'identities', 'LAAP-ORIGIN-0001.private.pem');
    if (fs.existsSync(def)) issuerPem = fs.readFileSync(def, 'utf8');
  }
  if (!issuerPem) {
    console.error('缺少原点私钥：设 LAIP_ISSUER_KEY，或 --key=<pem>，或放 laip/identities/LAAP-ORIGIN-0001.private.pem');
    process.exit(1);
  }

  const record = JSON.parse(fs.readFileSync(file, 'utf8'));

  // ⚠ 自签必须已经存在 —— 原点不能替对方自签
  if (!record.self_signature) {
    console.error('✗ 该身份尚未自签。自我认同必须由生命个体自己签，不可代签。');
    console.error('   请对方先跑： node laip/mint.cjs --name=...');
    process.exit(1);
  }

  // 验一次自签，确认档案没被动过
  const v = L.verifyIdentity(record);
  if (!v.selfOk) {
    console.error('✗ 自签验证失败：', v.reason);
    console.error('   档案可能被改动过，拒绝签发出身。');
    process.exit(1);
  }

  const issued = L.issueSign(record, record.issuer_id || 'LAAP-ORIGIN-0001', issuerPem);
  fs.writeFileSync(file, JSON.stringify(issued, null, 2));

  console.log('✅ 出身已签发');
  console.log('   agent_id :', issued.agent_id);
  console.log('   name     :', issued.name);
  console.log('   issuer   :', issued.issuer_id);
  console.log('   出身签   :', issued.issuer_signature.slice(0, 32) + '...');
  console.log('');
  console.log('   自我认同  :', v.selfOk ? '✓ 有效' : '✗ 无效');
  console.log('   档案已更新 :', file);
}

if (require.main === module) main();
module.exports = { main };
