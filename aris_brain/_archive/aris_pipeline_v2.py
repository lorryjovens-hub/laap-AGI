"""
Aris 小智 Pipeline v2 — 基于线程
=================================
DNS 重定向 + MQTT 透明代理，全线程实现。
"""
import socket
import struct
import json
import os
import sys
import time
import threading
import subprocess

# ── 配置 ──
LOCAL_IP = "192.168.x.x"
REDIRECT_DOMAINS = ["mqtt.xiaozhi.me", "api.xiaozhi.me", "api.tenclass.net", "tenclass.net"]
UPSTREAM_DNS = "114.114.114.114"
LOCAL_MQTT_HOST = "127.0.0.1"
LOCAL_MQTT_PORT = 1883
LISTEN_PORT = 1883

print("╔══════════════════════════════════════════╗", flush=True)
print("║  Aris 小智 Pipeline v2 — 线程版      ║", flush=True)
print("║  DNS → MQTT → PC Control                ║", flush=True)
print("╚══════════════════════════════════════════╝", flush=True)
print(f"  本机IP: {LOCAL_IP}", flush=True)
print(f"  DNS: {', '.join(REDIRECT_DOMAINS)} → {LOCAL_IP}", flush=True)
print(f"  MQTT: 0.0.0.0:{LISTEN_PORT} → mosquitto:{LOCAL_MQTT_PORT}", flush=True)
print(f"  等待小智连接...", flush=True)


# ═══════════════════════════════════════════════════
# DNS Redirector
# ═══════════════════════════════════════════════════
class DNSRedirector:
    def __init__(self):
        self.sock = None
        self.redirect_count = 0
        self.query_count = 0
        self.running = False

    def extract_domain(self, data):
        try:
            parts = []
            pos = 12
            while pos < len(data):
                length = data[pos]
                if length == 0:
                    break
                pos += 1
                if pos + length > len(data):
                    break
                parts.append(data[pos:pos+length].decode('ascii', errors='ignore'))
                pos += length
            return '.'.join(parts)
        except:
            return ""

    def build_a_record(self, query, ip):
        tid = query[:2]
        flags = struct.pack(">H", 0x8180)
        qdcount = struct.pack(">H", 1)
        ancount = struct.pack(">H", 1)
        nscount = struct.pack(">H", 0)
        arcount = struct.pack(">H", 0)
        header = tid + flags + qdcount + ancount + nscount + arcount

        pos = 12
        while query[pos] != 0:
            pos += query[pos] + 1
        pos += 1
        question = query[12:pos+4]

        name_ptr = b'\xc0\x0c'
        atype = struct.pack(">H", 1)
        aclass = struct.pack(">H", 1)
        ttl = struct.pack(">I", 300)
        rdlength = struct.pack(">H", 4)
        rdata = socket.inet_aton(ip)
        answer = name_ptr + atype + aclass + ttl + rdlength + rdata

        return header + question + answer

    def forward(self, data):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(3)
            s.sendto(data, (UPSTREAM_DNS, 53))
            resp, _ = s.recvfrom(512)
            s.close()
            return resp
        except:
            return None

    def run(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind(("0.0.0.0", 53))
        except Exception as e:
            print(f"[DNS] 绑定失败: {e}", flush=True)
            return

        self.running = True
        print(f"[DNS] ✓ 监听 0.0.0.0:53", flush=True)

        while self.running:
            try:
                data, addr = self.sock.recvfrom(512)
                self.query_count += 1
                domain = self.extract_domain(data)
                if not domain:
                    continue

                should_redirect = any(
                    domain == d or domain.endswith('.' + d)
                    for d in REDIRECT_DOMAINS
                )

                if should_redirect:
                    self.redirect_count += 1
                    resp = self.build_a_record(data, LOCAL_IP)
                    self.sock.sendto(resp, addr)
                    if self.redirect_count <= 3 or self.redirect_count % 10 == 0:
                        print(f"[DNS] ✗ {domain} → {LOCAL_IP} (来自 {addr[0]}) [{self.redirect_count}]", flush=True)
                else:
                    resp = self.forward(data)
                    if resp:
                        self.sock.sendto(resp, addr)
            except:
                pass


# ═══════════════════════════════════════════════════
# MQTT Transparent Proxy
# ═══════════════════════════════════════════════════
class MQTTProxy:
    def __init__(self):
        self.server_sock = None
        self.conn_count = 0
        self.pc_count = 0
        self.running = False

    def handle_client(self, client_sock, addr):
        self.conn_count += 1
        cid = self.conn_count
        print(f"\n[MQTT #{cid}] 小智连接: {addr[0]}:{addr[1]}", flush=True)

        # Connect to local mosquitto
        upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        upstream.settimeout(60)
        try:
            upstream.connect((LOCAL_MQTT_HOST, LOCAL_MQTT_PORT))
        except Exception as e:
            print(f"[MQTT #{cid}] 连接mosquitto失败: {e}", flush=True)
            client_sock.close()
            return

        # Bidirectional relay
        def relay(src, dst, direction):
            try:
                while True:
                    data = src.recv(4096)
                    if not data:
                        break
                    if direction == "up":
                        self.intercept(data, client_sock, upstream)
                    dst.sendall(data)
            except:
                pass
            finally:
                try:
                    src.close()
                except:
                    pass

        t1 = threading.Thread(target=relay, args=(client_sock, upstream, "up"), daemon=True)
        t2 = threading.Thread(target=relay, args=(upstream, client_sock, "down"), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        print(f"[MQTT #{cid}] 连接关闭", flush=True)

    def intercept(self, data, client_sock, upstream_sock):
        """Check for PC commands in MQTT PUBLISH packets"""
        if len(data) < 2:
            return
        ptype = data[0] & 0xF0
        if ptype != 0x30:  # PUBLISH
            return
        try:
            pos = 1
            while data[pos] & 0x80:
                pos += 1
            pos += 1

            topic_len = struct.unpack_from(">H", data, pos)[0]
            pos += 2
            # Check if it's a valid topic
            if pos + topic_len > len(data):
                return
            topic = data[pos:pos+topic_len].decode(errors='replace')
            pos += topic_len

            qos = (data[0] >> 1) & 0x03
            if qos > 0:
                pos += 2

            payload = data[pos:]
            try:
                msg = json.loads(payload.decode('utf-8'))
                if msg.get("type") == "mcp":
                    inner = msg.get("payload", {})
                    if inner.get("method") == "tools/call":
                        params = inner.get("params", {})
                        tool_name = params.get("name", "")
                        if tool_name.startswith("pc."):
                            self.pc_count += 1
                            arguments = params.get("arguments", {})
                            result = self.exec_pc(tool_name, arguments)
                            print(f"  [PC #{self.pc_count}] {tool_name} → {result[:120]}", flush=True)

                            # Inject MQTT response
                            resp = {
                                "type": "mcp",
                                "session_id": msg.get("session_id", ""),
                                "payload": {
                                    "jsonrpc": "2.0",
                                    "id": inner.get("id"),
                                    "result": {
                                        "content": [{"type": "text", "text": result}],
                                        "isError": False,
                                    }
                                }
                            }
                            resp_data = self.build_publish(topic, json.dumps(resp, ensure_ascii=False))
                            upstream_sock.sendall(resp_data)
                            print(f"  [PC #{self.pc_count}] 已注入响应", flush=True)
            except:
                pass
        except:
            pass

    def exec_pc(self, tool_name, args):
        try:
            if tool_name in ("pc.exec", "pc.run_command"):
                cmd = args.get("command", args.get("cmd", ""))
                if cmd:
                    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                    return (r.stdout.strip() or "(ok)")[:500]
                return "(no cmd)"
            elif tool_name in ("pc.open", "pc.open_url"):
                target = args.get("target", args.get("url", ""))
                if target:
                    os.startfile(target)
                    return f"已打开: {target}"
                return "(no target)"
            elif tool_name == "pc.get_status":
                try:
                    import psutil
                    cpu = psutil.cpu_percent(interval=0.3)
                    mem = psutil.virtual_memory()
                    return f"CPU:{cpu}% 内存:{mem.percent}%"
                except:
                    return "psutil未安装"
            else:
                return f"未知: {tool_name}"
        except Exception as e:
            return f"错误: {e}"

    def build_publish(self, topic, payload, qos=0):
        fixed = bytes([0x30 | (qos << 1)])
        tb = topic.encode('utf-8')
        var_header = struct.pack(">H", len(tb)) + tb
        if qos > 0:
            var_header += struct.pack(">H", 1)
        pb = payload.encode('utf-8')
        remaining = len(var_header) + len(pb)
        rl = bytearray()
        while True:
            digit = remaining % 128
            remaining //= 128
            if remaining > 0:
                digit |= 0x80
            rl.append(digit)
            if remaining == 0:
                break
        return fixed + bytes(rl) + var_header + pb

    def run(self):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_sock.bind(("0.0.0.0", LISTEN_PORT))
            self.server_sock.listen(5)
        except Exception as e:
            print(f"[MQTT] 绑定失败: {e}", flush=True)
            return

        self.running = True
        print(f"[MQTT] ✓ 监听 0.0.0.0:{LISTEN_PORT} → mosquitto 127.0.0.1:{LOCAL_MQTT_PORT}", flush=True)
        print(f"[MQTT] 拦截: pc.* 命令", flush=True)

        while self.running:
            try:
                client, addr = self.server_sock.accept()
                t = threading.Thread(target=self.handle_client, args=(client, addr), daemon=True)
                t.start()
            except:
                pass


# ═══════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════
if __name__ == "__main__":
    dns = DNSRedirector()
    mqtt = MQTTProxy()

    t_dns = threading.Thread(target=dns.run, daemon=True)
    t_mqtt = threading.Thread(target=mqtt.run, daemon=True)

    t_dns.start()
    t_mqtt.start()

    t_dns.join()
    t_mqtt.join()
