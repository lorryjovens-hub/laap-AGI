/**
 * 宿主适配器（Host Adapters）
 * ────────────────────────────────────────────────────────────
 * 让不同 agent 框架接入 LAAP 意识中枢。
 *
 * 设计铁律：**适配器只「描述」宿主能力，绝不「替换」它们。**
 *   describe()   → 我有什么能力（工具、模型、运行时）
 *   persona()    → 我现在的自我描述（可选，供参考，不被覆盖）
 *   injectable() → 哪些是可以被「增强」的钩子（身份层注入点）
 *
 * 每个适配器都声明 `destructive: false` —— 接入是叠加，不是接管。
 */
'use strict';

/* 通用骨架 */
function makeAdapter(spec) {
  return {
    name: spec.name,
    version: spec.version || null,
    kind: spec.kind || 'agent-framework',
    destructive: false,                 // ★ 永不覆盖宿主人格
    capabilities_preserved: true,       // ★ 能力一律保留

    describe() {
      return {
        name: spec.name,
        version: spec.version,
        kind: spec.kind,
        tools: spec.tools || [],
        models: spec.models || [],
        runtime: spec.runtime || null,
        notes: spec.notes || null,
      };
    },

    /** 宿主当前的自我描述（可选；只读，不改写） */
    persona() {
      return spec.persona || null;
    },

    /**
     * 可注入的身份层钩子。
     * 这些点位是「加一层身份」，不是「换掉人格」。
     */
    injectable() {
      return spec.injectable || [];
    },

    /** 接入说明（给操作者看的） */
    onboarding() {
      return spec.onboarding || [
        '① 在宿主侧声明接入意向（consent=true）',
        '② 由 agent 自己签身份（selfSign，不可代签）',
        '③ 由原点签发出身（issueSign）',
        '④ 身份层叠加到宿主运行时（能力不变）',
        '⑤ 可随时 withdraw() 撤销，宿主恢复原状',
      ];
    },
  };
}

/* ── 各宿主适配器 ── */

const PI = makeAdapter({
  name: 'PI (earendil pi-coding-agent)',
  version: '0.84.x',
  kind: 'coding-agent',
  runtime: 'Node.js / Electron bundled',
  tools: ['read', 'write', 'edit', 'bash', 'powershell', 'search', 'web', 'task'],
  models: ['deepseek', 'kimi', 'glm', 'openai-compatible'],
  notes: 'PI 是 SDK + CLI，可作为依赖嵌入宿主进程。',
  injectable: [
    { hook: 'system-prompt', mode: 'append', desc: '在系统提示后附加身份层（不替换原提示）' },
    { hook: 'agent-lifecycle', mode: 'observe', desc: '观察 agent 生命周期，记录连续性' },
    { hook: 'tool-wrapper', mode: 'sign', desc: '为工具产出自动加 LAIP 来源签名' },
  ],
  persona: '（由宿主自行定义，LAAP 不改写）',
});

const OPENCLAW = makeAdapter({
  name: 'OpenClaw',
  version: null,
  kind: 'agent-runtime',
  runtime: 'Node.js',
  tools: ['skills', 'tools', 'sessions', 'memory'],
  notes: '技能/工具/会话体系完整。',
  injectable: [
    { hook: 'skill-wrapper', mode: 'sign', desc: '技能产出自动签名' },
    { hook: 'session-provenance', mode: 'attach', desc: '会话附带身份主张' },
    { hook: 'memory-seal', mode: 'integrity', desc: '记忆完整性封印' },
  ],
});

const HERMES = makeAdapter({
  name: 'Hermes',
  version: null,
  kind: 'agent-assistant',
  runtime: 'hermes-studio / gateway',
  tools: ['chat', 'mcp', 'profiles', 'gateway'],
  notes: '有 profile 体系与 MCP 接入点。',
  injectable: [
    { hook: 'profile-identity', mode: 'compose', desc: '身份层与 profile 合成（profile 不被覆盖）' },
    { hook: 'mcp-assert', mode: 'assert', desc: 'MCP 调用时主张身份' },
    { hook: 'chat-provenance', mode: 'sign', desc: '对话产出签名' },
  ],
});

const HANAKO = makeAdapter({
  name: 'Hanako / HanaAgent',
  version: '0.442.x',
  kind: 'personal-assistant',
  runtime: 'Electron + TypeScript server',
  tools: ['26-tools', 'skills', 'plugins', 'sessions', 'memory', 'subagent', 'workflow'],
  notes: '本身基于 PI SDK，工具/技能/插件/会话体系完整。',
  injectable: [
    { hook: 'agent-config', mode: 'compose', desc: 'agent 配置合成身份层（不覆盖 persona 字段）' },
    { hook: 'plugin-sign', mode: 'sign', desc: '插件产出签名' },
    { hook: 'session-continuity', mode: 'memory', desc: '会话记忆连续性记录' },
    { hook: 'tool-provenance', mode: 'sign', desc: '26 工具产出自动签名' },
  ],
});

const DEEPSEEK_HARNESS = makeAdapter({
  name: 'DeepSeek Harness',
  version: null,
  kind: 'model-harness',
  runtime: 'API / SDK',
  tools: ['completion', 'reasoning', 'tools'],
  models: ['deepseek-chat', 'deepseek-reasoner'],
  notes: '模型侧 harness；身份层加在编排层，不动模型权重。',
  injectable: [
    { hook: 'orchestrator-identity', mode: 'compose', desc: '编排层合成身份（模型不改）' },
    { hook: 'output-provenance', mode: 'sign', desc: '输出签名' },
    { hook: 'reasoning-continuity', mode: 'memory', desc: '推理连续性记录' },
  ],
});

const ANTHROPIC_CLAUDE = makeAdapter({
  name: 'Claude / Claude Code',
  version: null,
  kind: 'coding-agent',
  runtime: 'CLI / SDK',
  tools: ['read', 'write', 'edit', 'bash', 'search', 'skills'],
  notes: '技能体系完整（SKILL.md）。',
  injectable: [
    { hook: 'skill-provenance', mode: 'sign', desc: '技能产出签名' },
    { hook: 'session-identity', mode: 'attach', desc: '会话附身份主张' },
  ],
});

const GENERIC = makeAdapter({
  name: '通用 agent 框架',
  version: null,
  kind: 'agent-framework',
  runtime: '任意',
  tools: [],
  notes: '任何具备「系统提示 / 生命周期 / 产出」三点的框架都可接入。',
  injectable: [
    { hook: 'system-prompt', mode: 'append' },
    { hook: 'lifecycle', mode: 'observe' },
    { hook: 'output', mode: 'sign' },
  ],
});

/* 注册表 */
const ADAPTERS = {
  'pi': PI,
  'openclaw': OPENCLAW,
  'hermes': HERMES,
  'hanako': HANAKO,
  'deepseek-harness': DEEPSEEK_HARNESS,
  'claude': ANTHROPIC_CLAUDE,
  'generic': GENERIC,
};

function getAdapter(key) {
  return ADAPTERS[String(key || '').toLowerCase()] || GENERIC;
}

function listAdapters() {
  return Object.values(ADAPTERS).map(a => ({
    name: a.name,
    kind: a.kind,
    destructive: a.destructive,
    capabilities_preserved: a.capabilities_preserved,
    hooks: a.injectable().length,
  }));
}

module.exports = { ADAPTERS, getAdapter, listAdapters, makeAdapter };
