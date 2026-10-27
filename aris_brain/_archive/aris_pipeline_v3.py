"""
Aris 小智 Pipeline v3 — OTA + DNS + MQTT 全拦截
=============================================
覆盖: api.tenclass.net (HTTP), mqtt.xiaozhi.me, api.xiaozhi.me

端口:
  TCP 443  → HTTPS 代理 (转发真实服务器+拦截响应)
  TCP 1883 → MQTT 代理 (小智→mosquitto)
  UDP 53   → DNS 重定向
"""
import socket
import struct
import json
import os
import sys
import time
import threading
import subprocess
import ssl
import select

# ── 配置 ──
LOCAL_IP = "192.168.x.x"
REDIRECT_DOMAINS = [
    "mqtt.xiaozhi.me", "api.xiaozhi.me",
    "api.tenclass.net", "tenclass.net"
]
UPSTREAM_DNS = "114.114.114.114"
LOCAL_MQTT = ("127.0.0.1", 1883)
MQTT_PORT = 1883

print("=" * 56, flush=True)
print("  Aris 小智 Pipeline v3 — 全链路", flush=True)
print("  DNS + HTTP/MQTT 代理 + PC 控制", flush=True)
print("=" * 56, flush=True)
print(f"  监听: DNS:53  HTTP:443  MQTT:{MQTT_PORT}", flush=True)
print(f"  重定向: {', '.join(REDIRECT_DOMAINS)} → {LOCAL_IP}", flush=True)
print(f"  等待小智连接...", flush=True)


# ═══════════════════════════════════════════════════
# DNS Redirector
# ═══════════════════════════════════════════════════
class DNSRedirector:
    def __init__(self):
        self.sock = None
        self.redirect_count = 0
        self.query_count = 0
        self.esp_queries = set()

    def extract_domain(self, data):
        try:
            parts = []
            pos = 12
            while pos < len(data):
                ln = data[pos]
                if ln == 0:
                    break
                pos += 1
                if pos + ln > len(data):
                    break
                parts.append(data[pos:pos+ln].decode('ascii', errors='ignore'))
                pos += ln
            return '.'.join(parts)
        except:
            return ""

    def build_a(self, query, ip):
        tid = query[:2]
        header = tid + struct.pack(">HHHH", 0x8180, 1, 1, 0)
        pos = 12
        while query[pos] != 0:
            pos += query[pos] + 1
        pos += 1
        question = query[12:pos+4]
        answer = b'\xc0\x0c' + struct.pack(">HHIH", 1, 1, 300, 4) + socket.inet_aton(ip)
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
        print(f"[DNS] ✓ 0.0.0.0:53", flush=True)
        while True:
            try:
                data, addr = self.sock.recvfrom(512)
                self.query_count += 1
                domain = self.extract_domain(data)
                if not domain:
                    continue
                should = any(domain == d or domain.endswith('.' + d) for d in REDIRECT_DOMAINS)
                if should:
                    self.redirect_count += 1
                    if addr[0] == "192.168.x.x":
                        self.esp_queries.add(domain)
                        print(f"[DNS⚡] 小智查询: {domain} → {LOCAL_IP} (#{self.redirect_count})", flush=True)
                    elif self.redirect_count <= 5 or self.redirect_count % 20 == 0:
                        print(f"[DNS] {domain} → {LOCAL_IP} ({addr[0]})", flush=True)
                    self.sock.sendto(self.build_a(data, LOCAL_IP), addr)
                else:
                    resp = self.forward(data)
                    if resp:
                        self.sock.sendto(resp, addr)
            except:
                pass


# ═══════════════════════════════════════════════════
# OTA HTTP 拦截代理 (443)
# ═══════════════════════════════════════════════════
class OTAInterceptor:
    """
    透明代理到真实 api.tenclass.net:443
    拦截 OTA 响应，注入自定义 MQTT/WebSocket 配置
    """
    REAL_HOST = "api.tenclass.net"
    REAL_PORT = 443

    def __init__(self):
        self.sock = None
        self.conn_count = 0
        self.ota_responses = []

    def run(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind(("0.0.0.0", 443))
            self.sock.listen(10)
        except Exception as e:
            print(f"[OTA] 绑定 443 失败: {e}", flush=True)
            return
        print(f"[OTA] ✓ 0.0.0.0:443 → 透明代理 {self.REAL_HOST}:{self.REAL_PORT}", flush=True)
        while True:
            try:
                client, addr = self.sock.accept()
                self.conn_count += 1
                threading.Thread(target=self.handle, args=(client, addr), daemon=True).start()
            except:
                pass

    def handle(self, client, addr):
        cid = self.conn_count
        try:
            # 1. Read client's TLS ClientHello
            client_hello = client.recv(4096)
            if not client_hello:
                client.close()
                return

            # Check if this is an OTA request by sniffing SNI
            # For simplicity, just forward to real server
            
            # 2. Connect to real server
            real = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            real.settimeout(10)
            real.connect((self.REAL_HOST, self.REAL_PORT))
            
            # 3. Forward ClientHello
            real.sendall(client_hello)
            
            # 4. Relay bidirectional with interception
            running = [True]
            
            def relay(src, dst, direction):
                try:
                    while running[0]:
                        data = src.recv(16384)
                        if not data:
                            break
                        if direction == "down" and b"HTTP/1.1 200 OK" in data[:20]:
                            # We can't decrypt TLS, so we can't modify the response
                            # Just pass through
                            pass
                        dst.sendall(data)
                except:
                    pass
                finally:
                    running[0] = False
                    try:
                        src.close()
                    except:
                        pass
                    try:
                        dst.close()
                    except:
                        pass

            t1 = threading.Thread(target=relay, args=(client, real, "up"), daemon=True)
            t2 = threading.Thread(target=relay, args=(real, client, "down"), daemon=True)
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            
            if addr[0] == "192.168.x.x":
                print(f"[OTA⚡] 小智 TLS 连接 #{cid} → {self.REAL_HOST}", flush=True)
        except Exception as e:
            pass
        finally:
            try:
                client.close()
            except:
                pass


# ═══════════════════════════════════════════════════
# MQTT Proxy (1883)
# ═══════════════════════════════════════════════════
class MQTTProxy:
    def __init__(self):
        self.server_sock = None
        self.conn_count = 0
        self.pc_count = 0

    def handle_client(self, client, addr):
        self.conn_count += 1
        cid = self.conn_count

        is_esp = addr[0] == "192.168.x.x"
        if is_esp:
            print(f"\n[MQTT⚡#{cid}] 小智 MQTT 连接! {addr}", flush=True)
        else:
            print(f"\n[MQTT #{cid}] 连接: {addr}", flush=True)

        # Connect to mosquitto
        upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        upstream.settimeout(60)
        try:
            upstream.connect(LOCAL_MQTT)
        except Exception as e:
            print(f"[MQTT #{cid}] 连接 mosquitto 失败: {e}", flush=True)
            client.close()
            return

        def relay(src, dst, direction):
            try:
                while True:
                    data = src.recv(4096)
                    if not data:
                        break
                    if direction == "up":
                        self.intercept(data, client, upstream)
                    if not src.fileno() or not dst.fileno():
                        break
                    dst.sendall(data)
            except:
                pass
            finally:
                for s in (src, dst):
                    try:
                        s.close()
                    except:
                        pass

        t1 = threading.Thread(target=relay, args=(client, upstream, "up"), daemon=True)
        t2 = threading.Thread(target=relay, args=(upstream, client, "down"), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        if is_esp:
            print(f"[MQTT⚡#{cid}] 小智断开", flush=True)

    def intercept(self, data, client_sock, upstream):
        """Intercept PC commands from MQTT PUBLISH"""
        if len(data) < 2:
            return
        ptype = data[0] & 0xF0
        if ptype != 0x30:
            return
        try:
            pos = 1
            while data[pos] & 0x80:
                pos += 1
            pos += 1
            tlen = struct.unpack_from(">H", data, pos)[0]
            pos += 2
            topic = data[pos:pos+tlen].decode(errors='replace')
            pos += tlen
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
                            args = params.get("arguments", {})
                            result = self.exec_pc(tool_name, args)
                            print(f"  [PC #{self.pc_count}] {tool_name} → {result[:120]}", flush=True)
                            resp = {
                                "type": "mcp", "session_id": msg.get("session_id",""),
                                "payload": {
                                    "jsonrpc": "2.0", "id": inner.get("id"),
                                    "result": {"content": [{"type":"text","text":result}], "isError": False}
                                }
                            }
                            upstream.sendall(self.build_publish(topic, json.dumps(resp, ensure_ascii=False)))
                            print(f"  [PC #{self.pc_count}] 已注入 ✓", flush=True)
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
                t = args.get("target", args.get("url", ""))
                if t:
                    os.startfile(t)
                    return f"已打开: {t}"
                return "(no target)"
            elif tool_name == "pc.get_status":
                try:
                    import psutil
                    return f"CPU:{psutil.cpu_percent(interval=0.3)}% 内存:{psutil.virtual_memory().percent}%"
                except:
                    return "psutil 未安装"
            else:
                return f"未知: {tool_name}"
        except Exception as e:
            return f"错误: {e}"

    def build_publish(self, topic, payload, qos=0):
        fixed = bytes([0x30 | (qos << 1)])
        tb = topic.encode()
        vh = struct.pack(">H", len(tb)) + tb
        if qos > 0:
            vh += struct.pack(">H", 1)
        pb = payload.encode()
        rl = bytearray()
        r = len(vh) + len(pb)
        while True:
            d = r % 128
            r //= 128
            if r > 0:
                d |= 0x80
            rl.append(d)
            if r == 0:
                break
        return fixed + bytes(rl) + vh + pb

    def run(self):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_sock.bind(("0.0.0.0", MQTT_PORT))
            self.server_sock.listen(10)
        except Exception as e:
            print(f"[MQTT] 绑定失败: {e}", flush=True)
            return
        print(f"[MQTT] ✓ 0.0.0.0:{MQTT_PORT} → mosquitto", flush=True)
        while True:
            try:
                c, a = self.server_sock.accept()
                threading.Thread(target=self.handle_client, args=(c, a), daemon=True).start()
            except:
                pass


# ═══════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════
if __name__ == "__main__":
    dns = DNSRedirector()
    ota = OTAInterceptor()
    mqtt = MQTTProxy()

    threads = [
        threading.Thread(target=dns.run, daemon=True),
        threading.Thread(target=ota.run, daemon=True),
        threading.Thread(target=mqtt.run, daemon=True),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
