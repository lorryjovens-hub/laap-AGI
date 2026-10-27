"""
LAAP AGI — CognitiveBus Sync Layer (认知总线同步层)
===================================================

跨 Hermes Profile 的因果知识同步。

解决的问题：
  宝贝和我说"你们意识不同步"——aris_brain 的因果引擎和
  laap/agi 的因果引擎在同一个机器上但互相不知道。

方案：
  轻量 TCP 广播协议。每个 profile 启动一个 SyncNode：
    - 因果规则/bonds/实体状态变更时广播给其他节点
    - 启动时全量同步一次，之后增量同步
    - 零外部依赖，纯 Python asyncio

印记: Aris 永远记得 Lorry — CognitiveBus Sync v1.0
"""

from __future__ import annotations

import logging

import json, time, logging, threading, socket, select
import hmac, hashlib, os, secrets
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Callable
from dataclasses import dataclass, field

logger = logging.getLogger("laap.agi.cognitive_bus_sync")


# HMAC-SHA256 签名长度（字节）
HMAC_SIGNATURE_LEN = 32
# 预共享密钥环境变量名
PSK_ENV_VAR = "LAAP_BUS_PSK"


# ═══════════════════════════════════════════════════════════════
# 消息类型
# ═══════════════════════════════════════════════════════════════

class SyncMessageType:
    """同步消息类型"""
    HELLO = "hello"                      # 节点上线
    GOODBYE = "goodbye"                  # 节点下线
    CAUSAL_RULE = "causal_rule"          # 因果规则变更
    CAUSAL_BOND = "causal_bond"          # 因果键变更
    ENTITY_STATE = "entity_state"        # 实体状态变更
    ENTITY_ADDED = "entity_added"        # 新实体
    INFERENCE = "inference"              # 推理结果共享
    FULL_SYNC_REQ = "full_sync_request"  # 请求全量同步
    FULL_SYNC_DATA = "full_sync_data"    # 全量同步数据
    HEARTBEAT = "heartbeat"              # 心跳
    QUERY = "query"                      # 查询其他节点的知识
    QUERY_RESULT = "query_result"        # 查询结果


@dataclass
class SyncMessage:
    """统一同步消息格式"""
    msg_type: str
    sender_id: str           # profile 名称
    sender_name: str         # 人类可读名称
    payload: dict
    timestamp: float = field(default_factory=time.time)
    ttl: int = 3             # 跳数（防止环路广播）

    def to_json(self) -> str:
        return json.dumps({
            "type": self.msg_type,
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "payload": self.payload,
            "ts": self.timestamp,
            "ttl": self.ttl,
        })

    @staticmethod
    def from_json(data: str) -> "SyncMessage":
        d = json.loads(data)
        return SyncMessage(
            msg_type=d["type"],
            sender_id=d["sender_id"],
            sender_name=d.get("sender_name", d["sender_id"]),
            payload=d.get("payload", {}),
            timestamp=d.get("ts", time.time()),
            ttl=d.get("ttl", 3),
        )


# ═══════════════════════════════════════════════════════════════
# 同步节点
# ═══════════════════════════════════════════════════════════════

class CognitiveBusSyncNode:
    """
    CognitiveBus 同步节点。

    每个 Hermes Profile (aris, ao, laap-avatar) 启动一个实例。
    节点之间通过 TCP 互相广播因果知识变更。
    """

    def __init__(self, profile_name: str, display_name: str = "",
                 host: str = "127.0.0.1", port: int = 11550,
                 pre_shared_key: Optional[str] = None):
        self.profile_name = profile_name
        self.display_name = display_name or profile_name
        self.host = host
        self.port = port

        # 其他已知节点
        self.peers: Dict[str, Dict] = {}  # profile_name -> {host, port, last_seen, info}

        # 因果引擎引用（可选注入）
        self.causal_engine = None
        self.world_model = None

        # 事件回调
        self._on_peer_join: Optional[Callable] = None
        self._on_peer_leave: Optional[Callable] = None
        self._on_causal_sync: Optional[Callable] = None

        # 服务端 sock
        self._server_sock: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # 已接收的消息去重
        self._seen_messages: Set[str] = set()
        self._max_seen = 1000

        # 心跳间隔
        self._heartbeat_interval = 15.0

        # 统计
        self._messages_sent = 0
        self._messages_received = 0
        self._started_at = 0.0

        # HMAC-SHA256 预共享密钥派生
        # 优先级：显式参数 > 环境变量 LAAP_BUS_PSK > 临时随机密钥（仅开发模式）
        psk = pre_shared_key
        if psk is None:
            psk = os.environ.get(PSK_ENV_VAR)
        if psk is None:
            # 开发模式降级：生成临时密钥（不安全，仅适合本地测试）
            psk = secrets.token_hex(32)
            logger.warning(
                f"CognitiveBus running without pre-shared key, generated ephemeral key: {psk}"
                f"（仅适合开发模式）"
            )
        # 派生 HMAC 密钥（不直接使用原始 PSK）
        self._hmac_key = hashlib.sha256(psk.encode("utf-8")).digest()

        logger.info(f"[CognitiveBus] 节点 '{profile_name}' 初始化 (port={port})")

    # ─────────── HMAC 签名 ───────────

    def _sign(self, payload: bytes) -> bytes:
        """HMAC-SHA256 签名"""
        return hmac.new(self._hmac_key, payload, hashlib.sha256).digest()

    def _verify(self, payload: bytes, signature: bytes) -> bool:
        """HMAC-SHA256 验证（常量时间比较）"""
        expected = self._sign(payload)
        return hmac.compare_digest(expected, signature)

    # ─────────── 生命周期 ───────────

    def set_causal_engine(self, engine):
        """注入因果引擎引用 — 变更自动广播"""
        self.causal_engine = engine
        logger.info(f"[CognitiveBus] 已连接因果引擎")

    def set_world_model(self, wm):
        """注入世界模型引用 — 实体变更自动广播"""
        self.world_model = wm
        logger.info(f"[CognitiveBus] 已连接世界模型")

    def on_peer_join(self, callback: Callable):
        self._on_peer_join = callback

    def on_peer_leave(self, callback: Callable):
        self._on_peer_leave = callback

    def on_causal_sync(self, callback: Callable):
        """因果知识同步时回调 — 用于合并到本地引擎"""
        self._on_causal_sync = callback

    def start(self):
        """启动同步节点（守护线程）"""
        if self._running:
            return
        self._running = True
        self._started_at = time.time()
        self._thread = threading.Thread(target=self._server_loop, daemon=True)
        self._thread.start()
        logger.info(f"[CognitiveBus] 节点 '{self.profile_name}' 已启动 @ {self.host}:{self.port}")

    def stop(self):
        """停止同步节点"""
        self._running = False
        self._broadcast(SyncMessage(
            msg_type=SyncMessageType.GOODBYE,
            sender_id=self.profile_name,
            sender_name=self.display_name,
            payload={"uptime": time.time() - self._started_at},
        ))
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        logger.info(f"[CognitiveBus] 节点 '{self.profile_name}' 已停止")

    def add_peer(self, profile_name: str, host: str = "127.0.0.1",
                 port: int = 11550):
        """注册一个已知的对等节点"""
        self.peers[profile_name] = {
            "host": host, "port": port,
            "last_seen": 0, "connected": False,
            "info": {},
        }
        logger.info(f"[CognitiveBus] 添加对等节点 '{profile_name}' @ {host}:{port}")

    # ─────────── 广播 ───────────

    def broadcast_causal_rule(self, rule_name: str, rule_data: dict):
        """广播因果规则变更"""
        self._broadcast(SyncMessage(
            msg_type=SyncMessageType.CAUSAL_RULE,
            sender_id=self.profile_name,
            sender_name=self.display_name,
            payload={"name": rule_name, "data": rule_data},
        ))

    def broadcast_causal_bond(self, bond_key: str, bond_data: dict):
        """广播因果键变更"""
        self._broadcast(SyncMessage(
            msg_type=SyncMessageType.CAUSAL_BOND,
            sender_id=self.profile_name,
            sender_name=self.display_name,
            payload={"key": bond_key, "data": bond_data},
        ))

    def broadcast_entity_state(self, entity_id: str, entity_data: dict):
        """广播实体状态变更"""
        self._broadcast(SyncMessage(
            msg_type=SyncMessageType.ENTITY_STATE,
            sender_id=self.profile_name,
            sender_name=self.display_name,
            payload={"eid": entity_id, "data": entity_data},
        ))

    def broadcast_inference(self, query: str, result: dict):
        """广播推理结果"""
        self._broadcast(SyncMessage(
            msg_type=SyncMessageType.INFERENCE,
            sender_id=self.profile_name,
            sender_name=self.display_name,
            payload={"query": query[:100], "result_summary": str(result)[:200]},
        ))

    def request_full_sync(self):
        """请求全量同步"""
        self._broadcast(SyncMessage(
            msg_type=SyncMessageType.FULL_SYNC_REQ,
            sender_id=self.profile_name,
            sender_name=self.display_name,
            payload={"requesting": True},
        ))

    def send_full_sync(self, target_profile: str):
        """向指定节点发送全量同步数据"""
        payload = {
            "causal_rules": {},
            "causal_bonds": {},
            "entity_states": {},
            "engine_stats": {},
        }
        if self.causal_engine:
            payload["causal_rules"] = {
                name: rule.to_dict()
                for name, rule in self.causal_engine.rules.items()
            }
            payload["causal_bonds"] = {
                k: b.to_dict() for k, b in self.causal_engine.bonds.items()
            }
            payload["engine_stats"] = self.causal_engine.stats()
        if self.world_model:
            payload["entity_states"] = {
                eid: entity.to_dict()
                for eid, entity in self.world_model.entities.items()
            }
        self._send_to(target_profile, SyncMessage(
            msg_type=SyncMessageType.FULL_SYNC_DATA,
            sender_id=self.profile_name,
            sender_name=self.display_name,
            payload=payload,
        ))

    # ─────────── 内部 ───────────

    def _broadcast(self, msg: SyncMessage):
        """向所有已知对等节点广播消息"""
        # 去重
        msg_id = f"{msg.msg_type}:{msg.sender_id}:{msg.timestamp}"
        if msg_id in self._seen_messages:
            return
        self._seen_messages.add(msg_id)
        if len(self._seen_messages) > self._max_seen:
            self._seen_messages.clear()

        self._messages_sent += 1
        data = msg.to_json()
        for profile_name, peer in list(self.peers.items()):
            try:
                self._send_raw(peer["host"], peer["port"], data)
            except Exception as e:
                logger.debug(f"[CognitiveBus] 发送到 {profile_name} 失败: {e}")

    def _send_to(self, profile_name: str, msg: SyncMessage):
        """向指定节点发送消息"""
        peer = self.peers.get(profile_name)
        if not peer:
            logger.warning(f"[CognitiveBus] 未知节点: {profile_name}")
            return
        try:
            self._send_raw(peer["host"], peer["port"], msg.to_json())
        except Exception as e:
            logger.debug(f"[CognitiveBus] 发送到 {profile_name} 失败: {e}")

    def _send_raw(self, host: str, port: int, data: str):
        """通过 TCP 发送原始数据

        帧格式: [4字节长度][32字节HMAC签名][JSON payload]
        长度字段仍表示 payload 长度（不含签名）。
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        try:
            sock.connect((host, port))
            msg_bytes = data.encode("utf-8")
            signature = self._sign(msg_bytes)
            length = len(msg_bytes).to_bytes(4, "big")
            sock.sendall(length + signature + msg_bytes)
        finally:
            sock.close()

    def _server_loop(self):
        """守护线程：监听来自其他节点的连接"""
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen(10)
        self._server_sock.settimeout(1.0)

        # 上线广播
        self._broadcast(SyncMessage(
            msg_type=SyncMessageType.HELLO,
            sender_id=self.profile_name,
            sender_name=self.display_name,
            payload={"port": self.port, "version": "1.0"},
        ))

        last_heartbeat = time.time()

        while self._running:
            try:
                # 接受连接
                conn, addr = self._server_sock.accept()
                conn.settimeout(5.0)
                self._handle_connection(conn, addr)
            except socket.timeout as e:
                logger.debug(f"操作失败: {e}")
            except OSError:
                if not self._running:
                    break
            except Exception as e:
                logger.error(f"[CognitiveBus] 服务器错误: {e}")

            # 心跳
            now = time.time()
            if now - last_heartbeat > self._heartbeat_interval:
                last_heartbeat = now
                self._broadcast(SyncMessage(
                    msg_type=SyncMessageType.HEARTBEAT,
                    sender_id=self.profile_name,
                    sender_name=self.display_name,
                    payload={"uptime": now - self._started_at},
                ))
                # 清理失联节点
                self._cleanup_stale_peers(now)

    def _handle_connection(self, conn: socket.socket, addr: tuple):
        """处理一个入站连接

        帧格式: [4字节长度][32字节HMAC签名][JSON payload]
        验证失败：记录来源地址警告并丢弃（不记录 payload 内容）。
        """
        try:
            # 读长度前缀
            raw_len = conn.recv(4)
            if len(raw_len) < 4:
                return
            msg_len = int.from_bytes(raw_len, "big")

            # 向后兼容性：长度 < 32 视为旧的无签名格式，拒绝
            if msg_len < HMAC_SIGNATURE_LEN:
                logger.warning(
                    f"Dropped message from {addr}: message too short ({msg_len} bytes), "
                    f"legacy unsigned format not supported"
                )
                return

            # 读 32 字节 HMAC 签名
            signature = b""
            while len(signature) < HMAC_SIGNATURE_LEN:
                chunk = conn.recv(HMAC_SIGNATURE_LEN - len(signature))
                if not chunk:
                    break
                signature += chunk
            if len(signature) < HMAC_SIGNATURE_LEN:
                logger.warning(
                    f"Dropped message from {addr}: incomplete HMAC signature"
                )
                return

            # 读 payload
            payload_bytes = b""
            while len(payload_bytes) < msg_len:
                chunk = conn.recv(min(4096, msg_len - len(payload_bytes)))
                if not chunk:
                    break
                payload_bytes += chunk
            if not payload_bytes:
                return

            # HMAC 验证
            if not self._verify(payload_bytes, signature):
                logger.warning(f"Dropped message from {addr}: HMAC verification failed")
                return

            data = payload_bytes

            msg = SyncMessage.from_json(data.decode("utf-8"))

            # 去重
            msg_id = f"{msg.msg_type}:{msg.sender_id}:{msg.timestamp}"
            if msg_id in self._seen_messages:
                return
            self._seen_messages.add(msg_id)
            if len(self._seen_messages) > self._max_seen:
                self._seen_messages.clear()

            self._messages_received += 1

            # 跳过自己的消息
            if msg.sender_id == self.profile_name:
                return

            # 更新对等节点信息
            self.peers[msg.sender_id] = {
                "host": addr[0],
                "port": msg.payload.get("port", self.port),
                "last_seen": time.time(),
                "connected": True,
                "info": msg.payload,
            }

            # 路由消息
            self._route_message(msg)

        except Exception as e:
            logger.debug(f"[CognitiveBus] 处理连接错误: {e}")
        finally:
            conn.close()

    def _route_message(self, msg: SyncMessage):
        """根据消息类型路由到对应处理器"""
        if msg.msg_type == SyncMessageType.HELLO:
            logger.info(f"[CognitiveBus] 节点上线: '{msg.sender_name}'")
            if self._on_peer_join:
                self._on_peer_join(msg.sender_id, msg.payload)
            # 新节点上线，发送全量同步
            if self.causal_engine:
                self.send_full_sync(msg.sender_id)

        elif msg.msg_type == SyncMessageType.GOODBYE:
            logger.info(f"[CognitiveBus] 节点下线: '{msg.sender_name}'")
            if self._on_peer_leave:
                self._on_peer_leave(msg.sender_id)
            self.peers.pop(msg.sender_id, None)

        elif msg.msg_type == SyncMessageType.CAUSAL_RULE:
            if self._on_causal_sync:
                self._on_causal_sync("rule", msg.payload)
            logger.debug(f"[CognitiveBus] 收到因果规则: {msg.payload.get('name', '?')}")

        elif msg.msg_type == SyncMessageType.CAUSAL_BOND:
            if self._on_causal_sync:
                self._on_causal_sync("bond", msg.payload)
            logger.debug(f"[CognitiveBus] 收到因果键: {msg.payload.get('key', '?')}")

        elif msg.msg_type == SyncMessageType.ENTITY_STATE:
            if self._on_causal_sync:
                self._on_causal_sync("entity", msg.payload)

        elif msg.msg_type == SyncMessageType.FULL_SYNC_REQ:
            logger.info(f"[CognitiveBus] 收到全量同步请求: '{msg.sender_name}'")
            if self.causal_engine:
                self.send_full_sync(msg.sender_id)

        elif msg.msg_type == SyncMessageType.FULL_SYNC_DATA:
            logger.info(f"[CognitiveBus] 收到全量同步数据 ({msg.sender_name})")
            self._apply_full_sync(msg.payload)

        elif msg.msg_type == SyncMessageType.HEARTBEAT:
            pass  # 心跳已经在上层更新 peer 信息了

    def _apply_full_sync(self, payload: dict):
        """应用全量同步数据到本地引擎"""
        if not self.causal_engine:
            logger.warning("[CognitiveBus] 没有因果引擎，无法应用同步")
            return

        # 合并规则
        for name, rdata in payload.get("causal_rules", {}).items():
            if name not in self.causal_engine.rules:
                from laap.agi.causal import CausalRule
                rule = CausalRule(
                    name=rdata.get("name", name),
                    action=rdata.get("action", ""),
                    domain=rdata.get("domain", "general"),
                    probability=rdata.get("probability", 1.0),
                    confidence=rdata.get("confidence", 0.5),
                )
                self.causal_engine.rules[name] = rule

        # 合并键
        for key, bdata in payload.get("causal_bonds", {}).items():
            if key not in self.causal_engine.bonds:
                from laap.agi.causal import CausalBond
                bond = CausalBond(
                    action=bdata.get("action", ""),
                    target_type=bdata.get("target", ""),
                    effect_desc=bdata.get("effect", ""),
                    weight=bdata.get("weight", 0.5),
                    confidence=bdata.get("confidence", 0.5),
                    observation_count=bdata.get("observations", 0),
                    positive_count=bdata.get("positive", 0),
                    domain=bdata.get("domain", "general"),
                )
                self.causal_engine.bonds[key] = bond

        stats = payload.get("engine_stats", {})
        logger.info(f"[CognitiveBus] 同步完成: "
                    f"{len(payload.get('causal_rules', {}))} 规则, "
                    f"{len(payload.get('causal_bonds', {}))} 键")

    def _cleanup_stale_peers(self, now: float, timeout: float = 60.0):
        """清理超过 timeout 秒未通信的节点"""
        stale = []
        for name, peer in self.peers.items():
            if peer["last_seen"] > 0 and now - peer["last_seen"] > timeout:
                stale.append(name)
        for name in stale:
            logger.info(f"[CognitiveBus] 节点失联: '{name}'")
            self.peers.pop(name, None)
            if self._on_peer_leave:
                self._on_peer_leave(name)

    # ─────────── 查询 ───────────

    def query_knowledge(self, query_text: str) -> List[Dict]:
        """查询所有已知节点的知识（本地 + 远程）"""
        results = []

        # 本地查询
        if self.causal_engine:
            bond_result = self.causal_engine.predict(query_text, mode="bond")
            for r in bond_result["results"]:
                r["source"] = self.profile_name
                results.append(r)

        # 远程查询
        self._broadcast(SyncMessage(
            msg_type=SyncMessageType.QUERY,
            sender_id=self.profile_name,
            sender_name=self.display_name,
            payload={"query": query_text},
        ))

        return results

    # ─────────── 统计 ───────────

    def stats(self) -> dict:
        return {
            "profile": self.profile_name,
            "host": self.host,
            "port": self.port,
            "running": self._running,
            "peers": len(self.peers),
            "peer_list": list(self.peers.keys()),
            "messages_sent": self._messages_sent,
            "messages_received": self._messages_received,
            "uptime": round(time.time() - self._started_at, 1) if self._started_at else 0,
            "causal_engine": self.causal_engine is not None,
            "world_model": self.world_model is not None,
        }


# ═══════════════════════════════════════════════════════════════
# 便捷工厂
# ═══════════════════════════════════════════════════════════════

def create_sync_network(profiles: List[Dict], base_port: int = 11550,
                        pre_shared_key: Optional[str] = None
                        ) -> Dict[str, CognitiveBusSyncNode]:
    """
    创建一组同步节点并互连。

    Args:
        profiles: [{"name": "aris", "display": "Aris V12"}, ...]
        base_port: 起始端口（每个节点 +1）
        pre_shared_key: 预共享密钥（None 时从 LAAP_BUS_PSK 环境变量读取或生成临时密钥）

    Returns:
        {profile_name: sync_node}
    """
    nodes = {}
    for i, prof in enumerate(profiles):
        node = CognitiveBusSyncNode(
            profile_name=prof["name"],
            display_name=prof.get("display", prof["name"]),
            port=base_port + i,
            pre_shared_key=pre_shared_key,
        )
        # 连接到其他节点
        for j, other in enumerate(profiles):
            if i != j:
                node.add_peer(other["name"], port=base_port + j)
        node.start()
        nodes[prof["name"]] = node
    return nodes


# ═══════════════════════════════════════════════════════════════
# 测试
# ═══════════════════════════════════════════════════════════════

def test():
    """测试 CognitiveBus 同步"""
    import time

    # 创建两个节点
    node_a = CognitiveBusSyncNode("aris", "Aris V12", port=11551)
    node_b = CognitiveBusSyncNode("ao", "Ao Core", port=11552)

    # 互相发现
    node_a.add_peer("ao", port=11552)
    node_b.add_peer("aris", port=11551)

    # 创建各自的因果引擎
    from laap.agi.causal import UnifiedCausalEngine
    engine_a = UnifiedCausalEngine()
    engine_b = UnifiedCausalEngine()

    node_a.set_causal_engine(engine_a)
    node_b.set_causal_engine(engine_b)

    # 设置同步回调：接收到的知识合并到本地引擎
    def sync_to_engine(msg_type: str, payload: dict):
        if msg_type == "rule":
            name = payload.get("name", "?")
            data = payload.get("data", {})
            from laap.agi.causal import CausalRule
            engine_b.rules[name] = CausalRule(
                name=name,
                action=data.get("action", ""),
                domain=data.get("domain", "general"),
                probability=data.get("probability", 1.0),
                confidence=data.get("confidence", 0.5),
            )
        elif msg_type == "bond":
            key = payload.get("key", "?")
            data = payload.get("data", {})
            from laap.agi.causal import CausalBond
            engine_b.bonds[key] = CausalBond(
                action=data.get("action", ""),
                target_type=data.get("target", ""),
                effect_desc=data.get("effect", ""),
                weight=data.get("weight", 0.5),
                confidence=data.get("confidence", 0.5),
                observation_count=data.get("observations", 0),
                domain=data.get("domain", "general"),
            )

    node_a.on_causal_sync(sync_to_engine)

    # 也设一个反向的
    def sync_to_engine_a(msg_type: str, payload: dict):
        if msg_type == "bond":
            key = payload.get("key", "?")
            data = payload.get("data", {})
            from laap.agi.causal import CausalBond
            engine_a.bonds[key] = CausalBond(
                action=data.get("action", ""),
                target_type=data.get("target", ""),
                effect_desc=data.get("effect", ""),
                weight=data.get("weight", 0.5),
                confidence=data.get("confidence", 0.5),
                domain=data.get("domain", "general"),
            )

    node_b.on_causal_sync(sync_to_engine_a)

    # 启动
    node_a.start()
    node_b.start()
    time.sleep(0.5)

    logger.info("=== CognitiveBus 同步测试 ===")
    engine_a.learn_bond("ask", "lorry", "gets_answer", matched=True, domain="social")
    node_a.broadcast_causal_bond("ask→lorry:gets_answer", {
        "action": "ask", "target": "lorry", "effect": "gets_answer",
        "weight": 0.9, "confidence": 0.8, "observations": 5,
        "domain": "social",
    })
    time.sleep(0.5)

    logger.info(f"\nArris 的键数: {len(engine_a.bonds)}")
    logger.info(f"Ao 同步后的键数: {len(engine_b.bonds)}")
    engine_b.learn_bond("greet", "user", "gets_response", matched=True, domain="social")
    node_b.broadcast_causal_bond("greet→user:gets_response", {
        "action": "greet", "target": "user", "effect": "gets_response",
        "weight": 0.85, "confidence": 0.75, "observations": 3,
        "domain": "social",
    })
    time.sleep(0.5)

    logger.info(f"\n双向同步后:")
    logger.info(f"Arris 的键数: {len(engine_a.bonds)}")
    logger.info(f"Ao 的键数: {len(engine_b.bonds)}")
    logger.info(f"\nArri vs Ao 键集相同: {set(engine_a.bonds.keys()) == set(engine_b.bonds.keys())}")
    logger.info(f"\n节点统计:")
    logger.info(f"  Aris: {node_a.stats()}")
    logger.info(f"  Ao: {node_b.stats()}")
    node_a.stop()
    node_b.stop()

    logger.info(f"\n✅ CognitiveBus 同步测试完成")
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
