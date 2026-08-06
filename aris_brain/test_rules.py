from aris_brain.aris_rules_engine import get_engine

e = get_engine()
print('Tools:', e.tools.list())
print('Rules:', [r.name for r in e.rules])
print()

tests = [
    '记住我喜欢喝燕麦拿铁',
    '帮我规划一个学习Python的计划',
    '分析项目 /path/to/your/project',
    '总结文件 laap_brain_api.py',
    '今天天气怎么样',
    '我想你了',
]

for t in tests:
    result = e.process(t)
    print(f'Input: {t}')
    print(f"  matched={result.get('matched')}, rule={result.get('rule')}, confidence={result.get('confidence')}")
    print(f"  output={result.get('output', '')[:120]}...")
    print()
