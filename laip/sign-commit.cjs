/**
 * LAIP 提交签名 —— 给 git commit 加可验证的来源块
 *
 * 用法：
 *   node laip/sign-commit.cjs --file=<commit-msg 文件>        （prepare-commit-msg 钩子）
 *   node laip/sign-commit.cjs --msg="feat: xxx"               （打印带签名的完整 message）
 *
 * 它做的事：在 commit message 末尾加一段 LAIP-Provenance 尾注，
 * 含生产者、内容指纹、时间戳、签名。任何人可验证。
 *
 * 不依赖 GPG —— 这是我们自己的身份协议，跨机器可验，不绑 GitHub 账号。
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

/** 取默认身份（当前 agent） */
function defaultIdentity() {
  const dir = path.join(__dirname, 'identities');
  const idFile = process.env.LAIP_AGENT_ID
    ? path.join(dir, process.env.LAIP_AGENT_ID + '.json')
    : path.join(dir, 'LAAP-AGENT-00001.json');
  const keyFile = idFile.replace(/\.json$/, '.private.pem');
  if (!fs.existsSync(idFile) || !fs.existsSync(keyFile)) return null;
  return {
    record: JSON.parse(fs.readFileSync(idFile, 'utf8')),
    privateKey: fs.readFileSync(keyFile, 'utf8'),
  };
}

/** 在 message 末尾追加 LAIP 尾注（幂等：已有则先去掉旧的） */
function attach(message, prov) {
  const clean = String(message).replace(/\nLAIP-Provenance:[\s\S]*$/, '').trimEnd();
  const lines = [
    '',
    'LAIP-Provenance: 1.0',
    '  producer: ' + prov.producer,
    '  content_hash: ' + prov.content_hash,
    '  timestamp: ' + prov.timestamp,
    '  charter_version: ' + (prov.charter_version || '-'),
    '  signature: ' + prov.signature,
  ];
  return clean + '\n' + lines.join('\n') + '\n';
}

/** 从 message 里解析出来源块 */
function parse(message) {
  const m = String(message).match(/LAIP-Provenance: 1\.0([\s\S]*?)$/);
  if (!m) return null;
  const blk = m[1];
  const get = k => {
    const r = blk.match(new RegExp(k + ':\\s*(\\S+)'));
    return r ? r[1] : null;
  };
  return {
    laip_provenance: '1.0',
    producer: get('producer'),
    content_hash: get('content_hash'),
    timestamp: get('timestamp'),
    charter_version: get('charter_version') === '-' ? null : get('charter_version'),
    signature: get('signature'),
  };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const self = defaultIdentity();
  if (!self) {
    console.error('找不到身份档案/私钥。先跑 node laip/mint.cjs --name=...');
    process.exit(1);
  }

  let message;
  if (args.file) {
    message = fs.readFileSync(args.file, 'utf8');
  } else if (args.msg) {
    message = args.msg;
  } else {
    console.error('必填 --file=<commit-msg> 或 --msg=<message>');
    process.exit(1);
  }

  const prov = L.signProvenance(message, self.record.agent_id, self.privateKey, self.record.charter && self.record.charter.version);
  const signed = attach(message, prov);

  if (args.file) {
    fs.writeFileSync(args.file, signed);
    console.log('✓ 已签名 commit:', self.record.agent_id, '(' + self.record.name + ')');
  } else {
    process.stdout.write(signed);
  }
}

/** 验证一份 commit message 的来源 */
function verifyMessage(message, producerPublicKey) {
  const prov = parse(message);
  if (!prov) return { valid: false, reason: '未找到 LAIP 来源块' };
  const body = String(message).replace(/\nLAIP-Provenance:[\s\S]*$/, '').trimEnd();
  return L.verifyProvenance(body, prov, producerPublicKey);
}

if (require.main === module) main();
module.exports = { attach, parse, verifyMessage };
