# -*- coding: utf-8 -*-
"""配音实测：调用 /api/audio/synthesize 触发 CosyVoice 加载与合成（验证修复）。"""
import io, json, sys, time, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 取一个存在的智能体 id
with urllib.request.urlopen('http://localhost:8080/api/agents', timeout=5) as r:
    agents = json.loads(r.read())
agent_id = ''
if isinstance(agents, list) and agents:
    agent_id = agents[0].get('id', '')
elif isinstance(agents, dict):
    lst = agents.get('agents') or agents.get('data') or []
    if lst:
        agent_id = lst[0].get('id', '')
print('使用 agent_id:', agent_id)

payload = json.dumps({"text": "你好，欢迎使用配音功能。这是一次路径修复后的验证测试。", "agent_id": agent_id}).encode('utf-8')
req = urllib.request.Request('http://localhost:8080/api/audio/synthesize', data=payload,
                             headers={'Content-Type': 'application/json'})
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=420) as r:
        got_finish = False
        for raw in r:
            line = raw.decode('utf-8', errors='replace').strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                print('非JSON行:', line[:80])
                continue
            typ = obj.get('type')
            if typ == 'start':
                print(f"[{time.time()-t0:.0f}s] start sample_rate={obj.get('sample_rate')}")
            elif typ == 'finish':
                print(f"[{time.time()-t0:.0f}s] finish chunk_count={obj.get('chunk_count')}")
                got_finish = True
                break
            elif typ == 'error':
                print(f"[{time.time()-t0:.0f}s] ERROR: {obj.get('message')}")
                break
        print('配音实测:', '成功' if got_finish else '失败')
        sys.exit(0 if got_finish else 1)
except Exception as e:
    print('请求异常:', e)
    sys.exit(1)
