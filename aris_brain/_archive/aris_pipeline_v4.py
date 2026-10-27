"""
Aris 小智 Pipeline v4 — 最小稳定版
"""
import socket, struct, json, os, threading, subprocess, sys, time

LOCAL_IP = "192.168.x.x"
REDIRECT = ["mqtt.xiaozhi.me", "api.xiaozhi.me", "api.tenclass.net", "tenclass.net"]
UP_DNS = "114.114.114.114"

dns_ok = threading.Event()
mqtt_ok = threading.Event()
dns_hits = []
log_lock = threading.Lock()

def log(msg):
    with log_lock:
        print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)

# ── DNS ──
def dns_thread():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", 5353))
        log("[DNS] ✓ 127.0.0.1:5353 (通过 portproxy 来自热点:53)")
        dns_ok.set()
    except Exception as e:
        log(f"[DNS] ✗ {e}")
        return
    
    def name(data):
        parts, pos = [], 12
        while pos < len(data):
            ln = data[pos]
            if ln == 0: break
            pos += 1
            if pos + ln > len(data): break
            parts.append(data[pos:pos+ln].decode('ascii','ignore'))
            pos += ln
        return '.'.join(parts)
    
    def reply(query_data, ip):
        tid = query_data[:2]
        h = tid + struct.pack(">HHHH", 0x8180, 1, 1, 0, 0)
        pos = 12
        while query_data[pos] != 0: pos += query_data[pos] + 1
        q = query_data[12:pos+5]
        a = b'\xc0\x0c' + struct.pack(">HHIH", 1, 1, 300, 4) + socket.inet_aton(ip)
        return h + q + a
    
    while True:
        try:
            data, addr = s.recvfrom(512)
            dom = name(data)
            if not dom: continue
            hit = any(dom == d or dom.endswith('.' + d) for d in REDIRECT)
            if hit:
                s.sendto(reply(data, LOCAL_IP), addr)
                if addr[0] == "192.168.x.x":
                    dns_hits.append(dom)
                    log(f"[DNS⚡] 小智查询: {dom} → {LOCAL_IP}")
            else:
                try:
                    fwd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    fwd.settimeout(3)
                    fwd.sendto(data, (UP_DNS, 53))
                    rsp, _ = fwd.recvfrom(512)
                    s.sendto(rsp, addr)
                    fwd.close()
                except: pass
        except: pass

# ── MQTT ──
def mqtt_thread():
    svr = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    svr.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        svr.bind(("0.0.0.0", 1883))
        svr.listen(10)
        log("[MQTT] ✓ 0.0.0.0:1883")
        mqtt_ok.set()
    except Exception as e:
        log(f"[MQTT] ✗ {e}")
        return
    
    conns = [0]
    
    def handle(c, addr):
        conns[0] += 1
        cid = conns[0]
        esp = addr[0] == "192.168.x.x"
        if esp: log(f"\n[MQTT⚡#{cid}] 小智连接! {addr}")
        else: log(f"[MQTT #{cid}] {addr}")
        
        up = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        up.settimeout(60)
        try:
            up.connect(("127.0.0.1", 1883))
        except:
            c.close()
            return
        
        done = [False]
        def rly(src, dst, direction):
            try:
                while not done[0]:
                    d = src.recv(4096)
                    if not d: break
                    dst.sendall(d)
            except: pass
            finally:
                done[0] = True
                for s in (src, dst):
                    try: s.close()
                    except: pass
        
        t1 = threading.Thread(target=rly, args=(c, up, "up"))
        t2 = threading.Thread(target=rly, args=(up, c, "down"))
        t1.start(); t2.start()
        t1.join(); t2.join()
        if esp: log(f"[MQTT⚡#{cid}] 断开")
    
    while True:
        try:
            c, a = svr.accept()
            threading.Thread(target=handle, args=(c, a), daemon=True).start()
        except: pass

# ── Main ──
log("=" * 50)
log("Aris 小智 Pipeline v4")
log("=" * 50)
log(f"DNS: {', '.join(REDIRECT)} → {LOCAL_IP}")
log(f"MQTT: 0.0.0.0:1883 → mosquitto 127.0.0.1:1883")

t1 = threading.Thread(target=dns_thread, daemon=True)
t2 = threading.Thread(target=mqtt_thread, daemon=True)
t1.start(); t2.start()

dns_ok.wait(timeout=5)
mqtt_ok.wait(timeout=5)

if dns_ok.is_set() and mqtt_ok.is_set():
    log("✓ 管道就绪! 等待小智连接...")
    # Self-test
    try:
        ts = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ts.settimeout(2)
        hdr = b'\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'
        q = b'\x04mqtt\x08xiaozhi\x02me\x00\x00\x01\x00\x01'
        ts.sendto(hdr+q, ("127.0.0.1", 53))
        r, _ = ts.recvfrom(512)
        log(f"  DNS自检: 返回 {len(r)} 字节 ✓")
        ts.close()
    except: log("  DNS自检: 超时 (Windows DNS缓存可能干扰)")
    
    try:
        ts = socket.socket()
        ts.settimeout(2)
        ts.connect(("127.0.0.1", 1883))
        log(f"  MQTT自检: 127.0.0.1:1883 可达 ✓")
        ts.close()
    except: log("  MQTT自检: 失败")
    
    while True:
        time.sleep(300)
        log(f"[心跳] DNS命中: {len(dns_hits)}, 小智DNS: {dns_hits[-5:] if dns_hits else '无'}")
else:
    log("✗ 启动失败")
    while True:
        time.sleep(60)
