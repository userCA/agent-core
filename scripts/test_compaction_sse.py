"""Send multi-round messages and check for context.compacted SSE events."""
import requests
import json
import sys
import time

BASE = "http://localhost:8001"
SESSION_ID = None

def send_message(msg: str, round_num: int):
    global SESSION_ID
    url = f"{BASE}/chat/stream"
    params = {"session_id": SESSION_ID} if SESSION_ID else {}

    try:
        resp = requests.post(url, params=params, json={"message": msg}, stream=True, timeout=120)
        resp.raise_for_status()
        full_text = ""
        compaction_events = []
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: ") or line == "data: [DONE]":
                continue
            try:
                data = json.loads(line[6:])
                if data.get("type") == "message.start" and not SESSION_ID:
                    SESSION_ID = data.get("sessionId", "")
                elif data.get("actionType") == "context.compacted":
                    compaction_events.append(data)
                    print(f"  [COMPACT] tokensBefore={data.get('tokensBefore')} tokensAfter={data.get('tokensAfter')} reason={data.get('reason')}")
                elif data.get("type") == "text" and data.get("phase") == "delta":
                    full_text += data.get("content", "")
                elif data.get("type") == "message.error":
                    err = data.get("error", {})
                    print(f"  [ERROR] {err.get('type')}: {err.get('message')}")
            except json.JSONDecodeError:
                pass
        print(f"  Round {round_num}: reply={full_text[:80]}... compaction_events={len(compaction_events)}")
        return len(compaction_events)
    except Exception as e:
        print(f"  Round {round_num}: FAILED - {e}")
        return 0

def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    print(f"Sending {n} rounds (session will accumulate)...\n")
    total_compactions = 0
    for i in range(1, n + 1):
        msg = f"请用200字左右详细介绍一下中国的第{i}个五年计划的主要内容和成就"
        print(f"Sending round {i}: {msg[:40]}...")
        c = send_message(msg, i)
        total_compactions += c
        if i < n:
            time.sleep(2)
    print(f"\nDone! Total compaction events received: {total_compactions}")

if __name__ == "__main__":
    main()
