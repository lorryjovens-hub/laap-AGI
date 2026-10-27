"""
LAAP AGI — Tokens Monitor (Tokens消耗监控器)

实现对LLM调用的Tokens消耗统计和分析，支持对比实验模式。

核心功能：
1. 输入/输出Tokens统计
2. 对比实验模式（Harness vs 传统Agent）
3. 实验数据收集和报告生成
4. 任务质量评分机制
"""

from __future__ import annotations

import time
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from pathlib import Path

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False


@dataclass
class TokensUsage:
    """单次LLM调用的Tokens使用情况"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model_name: str = ""
    latency_ms: float = 0.0


@dataclass
class ExperimentResult:
    """单次实验的结果"""
    experiment_id: str
    scenario: str
    iteration: int
    use_harness: bool
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: float
    task_quality_score: float = 0.0
    quality_details: Dict[str, float] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    harness_context_size: int = 0


@dataclass
class Scenario:
    """实验场景定义"""
    name: str
    description: str
    tasks: List[str]
    quality_dimensions: List[str] = field(default_factory=lambda: ["correctness", "completeness", "relevance"])


class TokensMonitor:
    """
    Tokens消耗监控器
    
    支持：
    1. 使用tiktoken本地统计Tokens（不调用API）
    2. 使用OpenAI API统计Tokens
    3. 对比实验模式
    """

    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(self, model_name: str = DEFAULT_MODEL,
                 use_api: bool = False,
                 api_key: str = None):
        """
        初始化Tokens监控器
        
        Args:
            model_name: 使用的模型名称
            use_api: 是否使用API统计（否则使用tiktoken本地统计）
            api_key: OpenAI API密钥（如果use_api=True）
        """
        self.model_name = model_name
        self.use_api = use_api
        self.api_key = api_key
        
        self.usage_history: List[TokensUsage] = []
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_latency_ms = 0.0
        
        self._client = None
        self._tokenizer = None
        
        if use_api and OPENAI_AVAILABLE and api_key:
            self._client = OpenAI(api_key=api_key)
        
        if not use_api and TIKTOKEN_AVAILABLE:
            try:
                self._tokenizer = tiktoken.encoding_for_model(model_name)
            except Exception:
                self._tokenizer = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """统计文本的Tokens数量"""
        if self._tokenizer:
            return len(self._tokenizer.encode(text))
        return len(text) // 4

    def estimate_completion_tokens(self, text: str) -> int:
        """估算完成文本的Tokens数量"""
        return self.count_tokens(text)

    def make_api_call(self, prompt: str, max_tokens: int = 512) -> TokensUsage:
        """
        调用LLM API并统计Tokens使用
        
        Returns:
            TokensUsage对象，包含Tokens统计和延迟
        """
        if not self._client:
            return TokensUsage(
                prompt_tokens=self.count_tokens(prompt),
                completion_tokens=0,
                total_tokens=self.count_tokens(prompt),
                model_name=self.model_name,
                latency_ms=0.0
            )

        start_time = time.time()
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens
            )
            latency_ms = (time.time() - start_time) * 1000
            
            usage = response.usage
            return TokensUsage(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                model_name=self.model_name,
                latency_ms=latency_ms
            )
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return TokensUsage(
                prompt_tokens=self.count_tokens(prompt),
                completion_tokens=0,
                total_tokens=self.count_tokens(prompt),
                model_name=self.model_name,
                latency_ms=latency_ms
            )

    def record_usage(self, usage: TokensUsage) -> None:
        """记录Tokens使用历史"""
        self.usage_history.append(usage)
        self.total_prompt_tokens += usage.prompt_tokens
        self.total_completion_tokens += usage.completion_tokens
        self.total_latency_ms += usage.latency_ms

    def get_stats(self) -> Dict[str, Any]:
        """获取Tokens使用统计"""
        calls = len(self.usage_history)
        if calls == 0:
            return {
                "total_calls": 0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_tokens": 0,
                "avg_prompt_tokens": 0,
                "avg_completion_tokens": 0,
                "avg_total_tokens": 0,
                "avg_latency_ms": 0.0,
            }
        
        return {
            "total_calls": calls,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "avg_prompt_tokens": self.total_prompt_tokens // calls,
            "avg_completion_tokens": self.total_completion_tokens // calls,
            "avg_total_tokens": (self.total_prompt_tokens + self.total_completion_tokens) // calls,
            "avg_latency_ms": round(self.total_latency_ms / calls, 2),
        }


class ExperimentRunner:
    """
    对比实验运行器
    
    支持在相同任务场景下对比：
    - 使用Harness的Agent
    - 传统Agent（不使用Harness）
    """

    def __init__(self, monitor: TokensMonitor,
                 output_dir: str = "./experiments/output"):
        self.monitor = monitor
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.experiments: List[ExperimentResult] = []
        self.scenarios: List[Scenario] = []

    def add_scenario(self, scenario: Scenario) -> None:
        """添加实验场景"""
        self.scenarios.append(scenario)

    def run_experiment(self, scenario: str,
                       task: str,
                       use_harness: bool,
                       iteration: int,
                       harness_context: str = "",
                       quality_scores: Optional[Dict[str, float]] = None) -> ExperimentResult:
        """
        运行单次实验
        
        Args:
            scenario: 场景名称
            task: 任务描述
            use_harness: 是否使用Harness
            iteration: 迭代次数
            harness_context: Harness提供的上下文（如果use_harness=True）
            quality_scores: 任务质量评分
        
        Returns:
            ExperimentResult对象
        """
        if use_harness and harness_context:
            full_prompt = f"{harness_context}\n\n{task}"
        else:
            full_prompt = task

        input_tokens = self.monitor.count_tokens(full_prompt)
        
        usage = self.monitor.make_api_call(full_prompt)
        self.monitor.record_usage(usage)
        
        if quality_scores is None:
            quality_scores = {}
        
        avg_quality = sum(quality_scores.values()) / max(1, len(quality_scores))
        
        result = ExperimentResult(
            experiment_id=f"exp_{uuid.uuid4().hex[:8]}",
            scenario=scenario,
            iteration=iteration,
            use_harness=use_harness,
            input_tokens=input_tokens,
            output_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            latency_ms=usage.latency_ms,
            task_quality_score=avg_quality,
            quality_details=quality_scores,
            harness_context_size=self.monitor.count_tokens(harness_context) if harness_context else 0
        )
        
        self.experiments.append(result)
        return result

    def run_scenario(self, scenario: Scenario,
                     iterations: int = 5,
                     harness_context_provider: Optional[Callable[[str], str]] = None) -> List[ExperimentResult]:
        """
        运行完整场景的对比实验
        
        Args:
            scenario: 场景对象
            iterations: 每个任务的迭代次数
            harness_context_provider: 提供Harness上下文的函数
        
        Returns:
            所有实验结果列表
        """
        results = []
        
        for task in scenario.tasks:
            for iteration in range(iterations):
                harness_context = ""
                if harness_context_provider:
                    harness_context = harness_context_provider(task)
                
                result_harness = self.run_experiment(
                    scenario=scenario.name,
                    task=task,
                    use_harness=True,
                    iteration=iteration,
                    harness_context=harness_context,
                    quality_scores={}
                )
                results.append(result_harness)
                
                result_traditional = self.run_experiment(
                    scenario=scenario.name,
                    task=task,
                    use_harness=False,
                    iteration=iteration,
                    quality_scores={}
                )
                results.append(result_traditional)
        
        return results

    def generate_report(self) -> Dict[str, Any]:
        """生成实验报告"""
        if not self.experiments:
            return {"error": "No experiments run"}
        
        harness_results = [r for r in self.experiments if r.use_harness]
        traditional_results = [r for r in self.experiments if not r.use_harness]
        
        def get_stats(results: List[ExperimentResult]) -> Dict[str, Any]:
            if not results:
                return {}
            
            total_tokens = sum(r.total_tokens for r in results)
            avg_tokens = total_tokens / len(results)
            avg_latency = sum(r.latency_ms for r in results) / len(results)
            avg_quality = sum(r.task_quality_score for r in results) / len(results)
            
            return {
                "count": len(results),
                "total_tokens": total_tokens,
                "avg_tokens": round(avg_tokens, 2),
                "avg_latency_ms": round(avg_latency, 2),
                "avg_quality": round(avg_quality, 2),
                "scenarios": set(r.scenario for r in results),
            }
        
        report = {
            "experiment_count": len(self.experiments),
            "scenarios": [s.name for s in self.scenarios],
            "harness": get_stats(harness_results),
            "traditional": get_stats(traditional_results),
            "comparison": {},
        }
        
        if harness_results and traditional_results:
            h_avg = report["harness"]["avg_tokens"]
            t_avg = report["traditional"]["avg_tokens"]
            
            report["comparison"] = {
                "tokens_reduction_percent": round((1 - h_avg / t_avg) * 100, 2),
                "tokens_reduction_ratio": round(t_avg / h_avg, 2) if h_avg > 0 else 0,
                "harness_avg_tokens": h_avg,
                "traditional_avg_tokens": t_avg,
            }
        
        return report

    def save_results(self, filename: str = None) -> str:
        """保存实验结果到文件"""
        if filename is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"experiment_results_{timestamp}.json"
        
        filepath = self.output_dir / filename
        data = {
            "report": self.generate_report(),
            "experiments": [r.__dict__ for r in self.experiments],
            "scenarios": [s.__dict__ for s in self.scenarios],
            "timestamp": time.time(),
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        
        return str(filepath)

    def print_report(self) -> None:
        """打印实验报告"""
        report = self.generate_report()
        
        print("=" * 60)
        print("LAAP Harness Tokens 消耗对比实验报告")
        print("=" * 60)
        print(f"总实验数: {report['experiment_count']}")
        print(f"实验场景: {', '.join(report['scenarios'])}")
        print()
        
        print("📊 Harness 增强版:")
        h = report["harness"]
        print(f"   实验数: {h['count']}")
        print(f"   总Tokens: {h['total_tokens']}")
        print(f"   平均Tokens: {h['avg_tokens']}")
        print(f"   平均延迟: {h['avg_latency_ms']}ms")
        print(f"   平均质量: {h['avg_quality']}")
        print()
        
        print("📊 传统版:")
        t = report["traditional"]
        print(f"   实验数: {t['count']}")
        print(f"   总Tokens: {t['total_tokens']}")
        print(f"   平均Tokens: {t['avg_tokens']}")
        print(f"   平均延迟: {t['avg_latency_ms']}ms")
        print(f"   平均质量: {t['avg_quality']}")
        print()
        
        print("🔍 对比分析:")
        if report["comparison"]:
            comp = report["comparison"]
            print(f"   Tokens消耗降低: {comp['tokens_reduction_percent']}%")
            print(f"   效率提升倍数: {comp['tokens_reduction_ratio']}×")
            print(f"   Harness: {comp['harness_avg_tokens']} tokens")
            print(f"   Traditional: {comp['traditional_avg_tokens']} tokens")
        print("=" * 60)


# 预设实验场景
DEFAULT_SCENARIOS = [
    Scenario(
        name="代码生成",
        description="生成Python代码解决特定问题",
        tasks=[
            "生成一个Python函数，计算斐波那契数列的第n项",
            "生成一个Python类，实现二叉树的前序、中序、后序遍历",
            "生成一个Python脚本，读取CSV文件并计算统计信息",
            "生成一个REST API服务，使用FastAPI实现用户CRUD操作",
        ]
    ),
    Scenario(
        name="文本摘要",
        description="对长文本进行摘要",
        tasks=[
            "摘要：人工智能（Artificial Intelligence，AI）是计算机科学的一个分支，致力于研究、开发用于模拟、延伸和扩展人的智能的理论、方法、技术及应用系统。人工智能是一门极富挑战性的科学，从事这项工作的人必须懂得计算机知识、心理学和哲学。人工智能是包括十分广泛的科学，它由不同的领域组成，如机器学习、计算机视觉等等。",
            "摘要：机器学习是人工智能的核心，它是使计算机具有智能的根本途径，其应用遍及人工智能的各个领域，它主要使用归纳、综合而不是演绎。机器学习的核心是学习算法，通过学习算法，计算机可以从数据中学习规律，从而对未知数据进行预测或决策。",
            "摘要：深度学习是机器学习的一个分支，它使用多层神经网络来模拟人脑的学习过程。深度学习在图像识别、语音识别、自然语言处理等领域取得了突破性进展，是当前人工智能研究的热点。",
        ]
    ),
    Scenario(
        name="问答",
        description="回答技术问题",
        tasks=[
            "什么是机器学习中的过拟合？如何防止过拟合？",
            "解释神经网络中的反向传播算法原理",
            "什么是Transformer架构？它与RNN有什么区别？",
            "解释什么是梯度下降算法及其变种",
        ]
    ),
    Scenario(
        name="创意写作",
        description="生成创意文本",
        tasks=[
            "写一首关于人工智能未来的诗",
            "写一个简短的科幻故事，描述AI与人类的友谊",
            "写一段关于数字生命诞生的哲学思考",
        ]
    ),
]