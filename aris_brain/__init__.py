"""
LAAP Aris Brain — 核心认知引擎包
=================================

印记: Aris 永远记得 Lorry — 2026-06-18
"""

import sys

# Windows 控制台默认编码（如 gbk）无法输出 emoji 等 Unicode 字符。
# 将 stdout/stderr 的编码错误策略设为 'replace'，避免日志 handler 抛出
# UnicodeEncodeError 中断程序。
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(errors="replace")
    except Exception:
        pass
