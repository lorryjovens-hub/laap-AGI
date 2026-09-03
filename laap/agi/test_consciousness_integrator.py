"""
测试脚本：意识整合器模块测试

验证 ConsciousnessHarness 的核心功能：
  1. ConsciousContext 数据类创建
  2. 人格初始化和情感状态
  3. 意识循环启动/停止
  4. 输入处理和意识上下文构建
  5. 系统提示意识注入生成
  6. 输出记录和认知片段完成
  7. 完整意识报告获取
"""

import asyncio
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from laap.agi.consciousness_integrator import ConsciousnessHarness, ConsciousContext
from laap.agi.affective_engine import PersonalityProfile


async def test_conscious_context():
    print("=" * 60)
    print("测试 1: ConsciousContext 数据类")
    print("=" * 60)

    ctx = ConsciousContext()
    assert ctx.conscious_contents == []
    assert ctx.emotional_state == {}
    assert ctx.mood_label == "neutral"
    assert ctx.cognitive_biases == {}
    assert ctx.self_report == {}
    assert ctx.reflection_summary == ""
    assert ctx.attention_focus == "idle"
    print("✓ ConsciousContext 默认值正确")

    ctx.conscious_contents = [{"id": "test", "type": "PERCEPTUAL"}]
    ctx.mood_label = "joyful"
    ctx.attention_focus = "perceptual_test"
    assert len(ctx.conscious_contents) == 1
    assert ctx.mood_label == "joyful"
    assert ctx.attention_focus == "perceptual_test"
    print("✓ ConsciousContext 属性赋值正确")


async def test_personality_initialization():
    print("\n" + "=" * 60)
    print("测试 2: 人格初始化和情感状态")
    print("=" * 60)

    harness = ConsciousnessHarness()
    assert harness.affective is None
    assert harness.personality is None

    harness.initialize_personality()
    assert harness.personality is not None
    assert harness.personality.name == "Default"
    assert harness.affective is not None
    print("✓ 默认人格初始化成功")

    custom_personality = PersonalityProfile(
        name="Custom",
        baseline=np.array([0.2, 0.1, 0.0, 0.3, -0.1]),
        sensitivity=np.array([1.2, 1.0, 0.8, 1.5, 1.0]),
    )
    harness2 = ConsciousnessHarness()
    harness2.initialize_personality(custom_personality)
    assert harness2.personality.name == "Custom"
    print("✓ 自定义人格初始化成功")

    mood = harness.affective.compute_mood()
    assert isinstance(mood, str)
    print(f"✓ 情感状态计算情绪: {mood}")

    biases = harness.affective.compute_cognitive_bias()
    assert isinstance(biases, dict)
    assert "optimism" in biases
    assert "risk_seeking" in biases
    print("✓ 认知偏差计算成功")


async def test_consciousness_loop():
    print("\n" + "=" * 60)
    print("测试 3: 意识循环启动/停止")
    print("=" * 60)

    harness = ConsciousnessHarness(tick_interval=0.1)

    await harness.start()
    assert harness.running is True
    assert harness.tick_task is not None
    print("✓ 意识循环启动成功")

    await asyncio.sleep(0.3)

    await harness.stop()
    assert harness.running is False
    assert harness.tick_task is None
    print("✓ 意识循环停止成功")


async def test_process_input():
    print("\n" + "=" * 60)
    print("测试 4: 输入处理和意识上下文构建")
    print("=" * 60)

    harness = ConsciousnessHarness()
    harness.initialize_personality()

    context = await harness.process_input("Hello, how are you?")
    assert isinstance(context, ConsciousContext)
    print("✓ 处理输入成功，返回 ConsciousContext")

    assert len(context.conscious_contents) > 0
    print(f"✓ 意识内容数量: {len(context.conscious_contents)}")

    assert context.mood_label is not None
    print(f"✓ 当前情绪: {context.mood_label}")

    assert "attention_focus" in dir(context)
    print(f"✓ 注意力焦点: {context.attention_focus}")

    positive_context = await harness.process_input("Great work! Excellent!")
    print(f"✓ 正面反馈后的情绪: {positive_context.mood_label}")

    negative_context = await harness.process_input("This is bad, there's an error!")
    print(f"✓ 负面反馈后的情绪: {negative_context.mood_label}")


async def test_system_prompt_addon():
    print("\n" + "=" * 60)
    print("测试 5: 系统提示意识注入生成")
    print("=" * 60)

    harness = ConsciousnessHarness()
    harness.initialize_personality()

    await harness.process_input("Can you help me with this task?")

    prompt_addon = harness.generate_system_prompt_addon()
    assert isinstance(prompt_addon, str)
    assert "【意识注入】" in prompt_addon
    print("✓ 意识注入提示生成成功")

    lines = prompt_addon.strip().split("\n")
    print("生成的意识注入内容:")
    for line in lines[:8]:
        print(f"  {line}")
    print("  ...")


async def test_record_output():
    print("\n" + "=" * 60)
    print("测试 6: 输出记录和认知片段完成")
    print("=" * 60)

    harness = ConsciousnessHarness()
    harness.initialize_personality()

    await harness.process_input("What's the weather today?")
    await harness.record_output("The weather is sunny today.", outcome="success", confidence=0.8)

    report = harness.get_consciousness_report()
    meta = report.get("meta_cognitive", {})
    assert meta.get("total_episodes") == 1
    print("✓ 输出记录成功，认知片段完成")

    await harness.process_input("Another question")
    await harness.record_output("Error: service unavailable", outcome="failure", confidence=0.2)

    report = harness.get_consciousness_report()
    meta = report.get("meta_cognitive", {})
    assert meta.get("total_episodes") == 2
    print("✓ 失败输出记录成功")


async def test_consciousness_report():
    print("\n" + "=" * 60)
    print("测试 7: 完整意识报告获取")
    print("=" * 60)

    harness = ConsciousnessHarness()
    harness.initialize_personality()

    await harness.process_input("Test input for report")
    await harness.record_output("Test output", outcome="success", confidence=0.7)

    report = harness.get_consciousness_report()
    assert isinstance(report, dict)

    assert "consciousness_harness" in report
    assert "global_workspace" in report
    assert "conscious_context" in report
    assert "meta_cognitive" in report
    assert "affective" in report
    assert "broadcast_history" in report
    print("✓ 意识报告包含所有必要字段")

    assert report["consciousness_harness"]["running"] is False
    print("✓ 意识循环状态正确")

    assert report["global_workspace"]["total_processes"] >= 1
    print(f"✓ 工作空间进程数量: {report['global_workspace']['total_processes']}")

    assert report["meta_cognitive"]["total_episodes"] == 1
    print("✓ 元认知数据正确")

    assert report["affective"]["state_vector"] is not None
    print(f"✓ 情感状态向量: {report['affective']['state_vector']}")


async def test_broadcast_callback():
    print("\n" + "=" * 60)
    print("测试 8: 广播回调机制")
    print("=" * 60)

    harness = ConsciousnessHarness()
    harness.initialize_personality()

    callback_received = []

    def test_callback(packet):
        callback_received.append(packet)

    harness.add_broadcast_callback(test_callback)

    await harness.process_input("Test broadcast")

    assert len(callback_received) >= 1
    print(f"✓ 广播回调收到 {len(callback_received)} 条消息")

    packet = callback_received[0]
    assert "timestamp" in packet
    assert "contents" in packet
    print("✓ 广播包结构正确")


async def main():
    print("\n" + "=" * 60)
    print("意识整合器模块测试套件")
    print("=" * 60)

    tests = [
        test_conscious_context,
        test_personality_initialization,
        test_consciousness_loop,
        test_process_input,
        test_system_prompt_addon,
        test_record_output,
        test_consciousness_report,
        test_broadcast_callback,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            await test()
            passed += 1
            print(f"\n✓ 测试 {test.__name__} 通过")
        except Exception as e:
            failed += 1
            print(f"\n✗ 测试 {test.__name__} 失败: {e}")
            import traceback

            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"测试结果: {passed}/{len(tests)} 通过")
    if failed > 0:
        print(f"失败: {failed}")
        sys.exit(1)
    else:
        print("所有测试通过！")


if __name__ == "__main__":
    asyncio.run(main())