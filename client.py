#!/usr/bin/env python3
"""NetNotify UDP client. Run one process per client/device."""
import argparse
import json
import socket
import threading
import time
import uuid
from datetime import datetime

MAX_PACKET_SIZE = 4096
HEARTBEAT_SECONDS = 10


def main():
    parser = argparse.ArgumentParser(description="NetNotify UDP notification client")
    parser.add_argument("--server", default="127.0.0.1", help="UDP server IP or hostname (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=9999, help="UDP server port (default: 9999)")
    parser.add_argument("--name", default="Client", help="Friendly client name")
    args = parser.parse_args()
    client_id = str(uuid.uuid4())
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)
    server = (args.server, args.port)
    stop = threading.Event()

    def send(payload):
        try:
            sock.sendto(json.dumps(payload, separators=(",", ":")).encode("utf-8"), server)
        except OSError as exc:
            print(f"[NETWORK ERROR] {exc}")

    def heartbeat_loop():
        while not stop.wait(HEARTBEAT_SECONDS):
            send({"type": "heartbeat", "client_id": client_id})

    print("=" * 56)
    print(" NetNotify | UDP Notification Client")
    print(f" Name: {args.name} | Server: {args.server}:{args.port}")
    print(" Press Ctrl+C to disconnect.")
    print("=" * 56)
    send({"type": "register", "client_id": client_id, "name": args.name})
    thread = threading.Thread(target=heartbeat_loop, daemon=True)
    thread.start()
    try:
        while True:
            try:
                raw, address = sock.recvfrom(MAX_PACKET_SIZE + 1)
            except socket.timeout:
                continue
            if len(raw) > MAX_PACKET_SIZE:
                continue
            try:
                packet = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            kind = packet.get("type") if isinstance(packet, dict) else None
            if kind == "registered":
                print(f"[CONNECTED] Registered with server at {address[0]}:{address[1]} | ID {client_id[:8]}")
            elif kind == "notification":
                notification_id = str(packet.get("notification_id", ""))
                severity = str(packet.get("severity", "INFO")).upper()
                title = str(packet.get("title", "Notification"))[:100]
                body = str(packet.get("body", ""))[:500]
                created_at = str(packet.get("created_at", ""))
                print("\n" + "-" * 56)
                print(f"[{severity}] {title}")
                print(body)
                print(f"Time: {created_at or datetime.now().isoformat(timespec='seconds')}")
                print("-" * 56, flush=True)
                send({"type": "ack", "client_id": client_id, "notification_id": notification_id})
    except KeyboardInterrupt:
        print("\n[DISCONNECTED] NetNotify client stopped.")
    finally:
        stop.set()
        sock.close()


if __name__ == "__main__":
    main()
