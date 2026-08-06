"""
测试脚本 — 元认知监控器功能验证

运行方式：python -m laap.agi.test_meta_cognitive
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from laap.agi.meta_cognitive import (
    MetaCognitiveMonitor,
    CognitiveEpisode,
    ReflectionTrigger,
)


def test_cognitive_episode():
    """测试认知片段数据类"""
    print("=" * 60)
    print("测试 1: CognitiveEpisode 数据类")
    print("=" * 60)

    episode = CognitiveEpisode(context="测试上下文")
    episode.reasoning_trace = ["步骤1", "步骤2"]
    episode.action_taken = "执行测试"
    episode.outcome = "success"
    episode.confidence = 0.8

    assert episode.episode_id.startswith("ep_")
    assert episode.context == "测试上下文"
    assert len(episode.reasoning_trace) == 2
    assert episode.confidence == 0.8

    data = episode.to_dict()
    assert "episode_id" in data
    assert data["confidence"] == 0.8
    assert data["reasoning_steps"] == 2

    print("✓ CognitiveEpisode 创建成功")
    print(f"  episode_id: {episode.episode_id}")
    print(f"  to_dict(): {data}")
    print()


def test_meta_cognitive_monitor_basic():
    """测试元认知监控器基本功能"""
    print("=" * 60)
    print("测试 2: MetaCognitiveMonitor 基本功能")
    print("=" * 60)

    monitor = MetaCognitiveMonitor()

    episode_id = monitor.start_episode("测试任务：计算 2+2")
    assert episode_id.startswith("ep_")
    assert monitor.current_episode is not None

    monitor.record_reasoning("2加2等于4")
    monitor.record_reasoning("这是基本算术")
    assert len(monitor.current_episode.reasoning_trace) == 2

    monitor.record_action("返回结果4", "success", confidence=0.95)
    assert monitor.current_episode.action_taken == "返回结果4"
    assert monitor.current_episode.outcome == "success"
    assert monitor.current_episode.confidence == 0.95

    episode = monitor.end_episode()
    assert episode is not None
    assert episode.duration_ms > 0
    assert monitor.current_episode is None

    print("✓ 基本功能测试通过")
    print(f"  episode_id: {episode_id}")
    print(f"  推理步骤: {len(episode.reasoning_trace)}")
    print(f"  耗时: {episode.duration_ms:.1f}ms")
    print()


def test_auto_reflection_triggers():
    """测试自动反思触发机制"""
    print("=" * 60)
    print("测试 3: 自动反思触发机制")
    print("=" * 60)

    monitor = MetaCognitiveMonitor()

    episode_id = monitor.start_episode("低置信度任务")
    monitor.record_reasoning("不太确定答案")
    monitor.record_action("猜测答案", "结果未知", confidence=0.2)
    episode = monitor.end_episode()

    assert len(monitor.reflections) >= 1
    reflection = monitor.reflections[-1]
    assert ReflectionTrigger.CONFIDENCE_LOW.value in reflection["triggers"]

    print("✓ 低置信度触发反思")
    print(f"  触发类型: {reflection['triggers']}")
    print(f"  检测到偏差: {reflection['biases_detected']}")
    print()

    episode_id2 = monitor.start_episode("失败任务")
    monitor.record_reasoning("尝试执行")
    monitor.record_action("执行操作", "error: 失败", confidence=0.5)
    episode2 = monitor.end_episode()

    assert len(monitor.reflections) >= 2
    reflection2 = monitor.reflections[-1]
    assert ReflectionTrigger.ERROR_DETECTED.value in reflection2["triggers"]

    print("✓ 错误检测触发反思")
    print(f"  触发类型: {reflection2['triggers']}")
    print()


def test_bias_detection():
    """测试认知偏差检测"""
    print("=" * 60)
    print("测试 4: 认知偏差检测")
    print("=" * 60)

    monitor = MetaCognitiveMonitor()

    episode_id = monitor.start_episode("确认偏差测试")
    monitor.record_reasoning("这个数据支持我的观点")
    monitor.record_reasoning("没有反例可以反驳")
    monitor.record_action("提交结论", "success", confidence=0.2)
    episode = monitor.end_episode()

    biases = monitor.cognitive_biases_detected
    assert len(biases) >= 1
    assert "confirmation_bias" in biases[-1]["biases"]

    print("✓ 确认偏差检测成功")
    print(f"  检测到偏差: {biases[-1]['biases']}")
    print()

    episode_id2 = monitor.start_episode("推理不足测试")
    monitor.record_reasoning("直接得出结论")
    monitor.record_action("快速决策", "success", confidence=0.2)
    episode2 = monitor.end_episode()

    biases2 = monitor.cognitive_biases_detected
    assert "insufficient_reasoning" in biases2[-1]["biases"]

    print("✓ 推理不足检测成功")
    print(f"  检测到偏差: {biases2[-1]['biases']}")
    print()

    episode_id3 = monitor.start_episode("过度自信测试")
    monitor.record_reasoning("这个方案绝对正确")
    monitor.record_reasoning("毫无疑问会成功")
    monitor.record_action("执行方案", "success", confidence=0.95)
    episode3 = monitor.end_episode()

    biases3 = monitor.cognitive_biases_detected
    assert "overconfidence" in biases3[-1]["biases"]

    print("✓ 过度自信检测成功")
    print(f"  检测到偏差: {biases3[-1]['biases']}")
    print()


def test_circularity_detection():
    """测试循环推理检测"""
    print("=" * 60)
    print("测试 5: 循环推理检测")
    print("=" * 60)

    monitor = MetaCognitiveMonitor()

    episode_id = monitor.start_episode("循环推理测试")
    monitor.record_reasoning("A因为B")
    monitor.record_reasoning("B因为C")
    monitor.record_reasoning("C因为A")
    monitor.record_action("提交循环论证", "success", confidence=0.2)
    episode = monitor.end_episode()

    assert len(monitor.reflections) >= 1
    reflection = monitor.reflections[-1]
    assert reflection["circularity_detected"] == True

    print("✓ 循环推理检测成功")
    print(f"  circularity_detected: {reflection['circularity_detected']}")
    print()


def test_self_report():
    """测试自我报告生成"""
    print("=" * 60)
    print("测试 6: 自我报告生成")
    print("=" * 60)

    monitor = MetaCognitiveMonitor()

    for i in range(5):
        episode_id = monitor.start_episode(f"任务 {i+1}")
        monitor.record_reasoning(f"分析任务 {i+1}")
        monitor.record_reasoning(f"制定策略 {i+1}")
        outcome = "success" if i % 2 == 0 else "partial success"
        confidence = 0.8 + (i % 3) * 0.1
        monitor.record_action(f"执行任务 {i+1}", outcome, confidence=confidence)
        monitor.end_episode()

    report = monitor.get_self_report()

    assert "meta_cognitive_report" in report
    assert report["meta_cognitive_report"]["total_episodes"] == 5
    assert report["meta_cognitive_report"]["total_reflections"] >= 1
    assert "bias_distribution" in report
    assert "learning_points" in report

    print("✓ 自我报告生成成功")
    print(f"  总片段数: {report['meta_cognitive_report']['total_episodes']}")
    print(f"  成功率: {report['meta_cognitive_report']['success_rate']:.0%}")
    print(f"  平均置信度: {report['meta_cognitive_report']['average_confidence']:.0%}")
    print()


def test_introspection_prompt():
    """测试内省提示生成"""
    print("=" * 60)
    print("测试 7: 内省提示生成")
    print("=" * 60)

    monitor = MetaCognitiveMonitor()

    for i in range(3):
        episode_id = monitor.start_episode(f"内省测试任务 {i+1}")
        monitor.record_reasoning("分析问题")
        monitor.record_action("执行", "success", confidence=0.75)
        monitor.end_episode()

    prompt = monitor.generate_introspection_prompt()

    assert "元认知内省提示" in prompt
    assert "累计完成" in prompt
    assert "成功率" in prompt

    print("✓ 内省提示生成成功")
    print("-" * 40)
    print(prompt)
    print("-" * 40)
    print()


def test_learning_points():
    """测试学习要点提取"""
    print("=" * 60)
    print("测试 8: 学习要点提取")
    print("=" * 60)

    monitor = MetaCognitiveMonitor()

    episode_id = monitor.start_episode("学习要点测试")
    monitor.record_reasoning("步骤太少")
    monitor.record_action("快速决策", "error: 失败", confidence=0.25)
    episode = monitor.end_episode()

    points = monitor._extract_learning_points(episode)

    assert len(points) >= 2
    assert "置信度低" in points[0]
    assert "推理步骤不足" in points[1]

    print("✓ 学习要点提取成功")
    print(f"  学习要点: {points}")
    print()


def test_reasoning_analysis():
    """测试推理分析"""
    print("=" * 60)
    print("测试 9: 推理分析")
    print("=" * 60)

    monitor = MetaCognitiveMonitor()

    episode_id = monitor.start_episode("推理分析测试")
    monitor.record_reasoning("目标是解决这个问题")
    monitor.record_reasoning("有两个备选方案：A和B")
    monitor.record_reasoning("根据数据显示，方案A更好")
    monitor.record_reasoning("选择方案A")
    monitor.record_action("执行方案A", "success", confidence=0.2)
    episode = monitor.end_episode()

    assert len(monitor.reflections) >= 1
    reflection = monitor.reflections[-1]
    analysis = reflection["reasoning_analysis"]

    assert analysis["step_count"] == 4
    assert analysis["has_goal_mention"] == True
    assert analysis["has_alternatives"] == True
    assert analysis["has_evidence"] == True
    assert analysis["depth_score"] > 0.3

    print("✓ 推理分析成功")
    print(f"  步骤数: {analysis['step_count']}")
    print(f"  提及目标: {analysis['has_goal_mention']}")
    print(f"  考虑备选: {analysis['has_alternatives']}")
    print(f"  引用证据: {analysis['has_evidence']}")
    print(f"  深度分数: {analysis['depth_score']}")
    print()


def test_llm_reflection_mock():
    """测试 LLM 深度反思（模拟）"""
    print("=" * 60)
    print("测试 10: LLM 深度反思（模拟）")
    print("=" * 60)

    class MockLLMClient:
        def complete(self, prompt):
            return "这是一个模拟的LLM反思结果。推理过程看起来合理，但可以增加更多备选方案的分析。"

    monitor = MetaCognitiveMonitor(llm_client=MockLLMClient())

    episode_id = monitor.start_episode("LLM反思测试")
    monitor.record_reasoning("分析问题")
    monitor.record_reasoning("制定方案")
    monitor.record_action("执行", "success", confidence=0.2)
    episode = monitor.end_episode()

    assert len(monitor.reflections) >= 1
    reflection = monitor.reflections[-1]

    assert "llm_insight" in reflection
    assert "模拟的LLM反思结果" in reflection["llm_insight"]

    print("✓ LLM深度反思测试通过")
    print(f"  LLM洞察: {reflection['llm_insight'][:80]}...")
    print()


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("  元认知监控器模块测试套件")
    print("=" * 60 + "\n")

    tests = [
        test_cognitive_episode,
        test_meta_cognitive_monitor_basic,
        test_auto_reflection_triggers,
        test_bias_detection,
        test_circularity_detection,
        test_self_report,
        test_introspection_prompt,
        test_learning_points,
        test_reasoning_analysis,
        test_llm_reflection_mock,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} 失败: {e}")
            failed += 1

    print("=" * 60)
    print(f"测试结果: {passed}/{len(tests)} 通过")
    if failed > 0:
        print(f"失败数: {failed}")
        sys.exit(1)
    else:
        print("所有测试通过！")
        sys.exit(0)


if __name__ == "__main__":
    main()