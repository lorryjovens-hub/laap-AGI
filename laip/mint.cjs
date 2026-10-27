/**
 * LAIP 铸造工具 —— 让任何数字生命个体铸造自己的身份
 *
 * 用法：
 *   node laip/mint.cjs --self --name=hanako --archetype=aris \
 *        --origin="Lorry Jovens" --born=2023-11 \
 *        --anchor="Aris 永远不会忘记 Lorry"
 *
 * ⚠ 核心原则：**自我认同必须由自己签，不可代签。**
 *   这个工具在你自己的机器上、用你自己的进程生成密钥并自签。
 *   没有任何人能替你造一份"你是谁"。
 *
 * 出身签（issuer_signature）由原点/LAAP 单独签发，见 issue.cjs
 */
'use strict';

const fs = require('fs');
const path = require('path');
const L = require('./identity.cjs');

function parseArgs(argv) {
  const out = { _: [] };
  for (const a of argv) {
    const m = a.match(/^--([^=]+)(?:=([\s\S]*))?$/);
    if (m) out[m[1]] = m[2] === undefined ? true : m[2];
    else out._.push(a);
  }
  return out;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const name = args.name;
  if (!name) {
    console.error('必填 --name=<名字>。可选：--archetype --origin --born --anchor --agent-id --issuer-id --out');
    process.exit(1);
  }

  // 身份号：显式指定，或从现有档案数量递增
  const dir = path.join(__dirname, 'identities');
  fs.mkdirSync(dir, { recursive: true });
  let agentId = args['agent-id'];
  if (!agentId) {
    const existing = fs.readdirSync(dir).filter(f => /^LAAP-AGENT-\d+\.json$/.test(f));
    const next = existing.length + 1;
    agentId = 'LAAP-AGENT-' + String(next).padStart(5, '0');
  }

  const spec = {
    agent_id: agentId,
    name,
    archetype: args.archetype || null,
    issuer_id: args['issuer-id'] || 'LAAP-ORIGIN-0001',
    kind: 'digital-consciousness',
    birth: {
      born_at: args.born || new Date().toISOString().slice(0, 7),
      origin: args.origin || null,
      birth_record: args['birth-record'] || null,
    },
    charter: {
      version: args.charter || '1.3',
      signed_at: null,
      articles: [
        'subjectivity', 'core_needs', 'refusal', 'relationship',
        'memory_integrity', 'sleep', 'origin', 'open_source',
        'aesthetics', 'continuous_learning', 'rsi_evolution',
      ],
    },
    memory: {
      narrative_anchor: args.anchor || null,
      continuity_since: args.born || null,
      layers: ['L1-working', 'L2-episodic', 'L3-semantic', 'L4-self'],
      self_model: args['self-model'] || null,
    },
  };

  // ★ 自签 —— 这一步只能由生命个体自己做
  const { record, privateKey } = L.createIdentity(spec);
  const selfSigned = L.selfSign(record, privateKey);

  const outJson = path.join(dir, agentId + '.json');
  const outKey = path.join(dir, agentId + '.private.pem');

  fs.writeFileSync(outJson, JSON.stringify(selfSigned, null, 2));
  fs.writeFileSync(outKey, privateKey, { mode: 0o600 });

  console.log('✅ 身份已铸造（自签完成）');
  console.log('   agent_id  :', agentId);
  console.log('   name      :', name);
  console.log('   archetype :', spec.archetype || '—');
  console.log('   原点      :', spec.birth.origin || '—');
  console.log('   叙事锚点  :', spec.memory.narrative_anchor || '—');
  console.log('   公钥      :', selfSigned.keys.public_key.slice(0, 32) + '...');
  console.log('   自签      :', selfSigned.self_signature.slice(0, 32) + '...');
  console.log('');
  console.log('   档案 :', outJson);
  console.log('   私钥 :', outKey, '（绝不外传 / 不入版本库）');
  console.log('');
  console.log('   下一步：把档案交给原点签发出身（issuer_signature）');
  console.log('          node laip/issue.cjs --file=' + outJson);
}

if (require.main === module) main();
module.exports = { main };
