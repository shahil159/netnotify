#!/usr/bin/env python3
"""NetNotify: Flask dashboard + UDP notification coordinator."""
import json
import os
import secrets
import socket
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("NETNOTIFY_DB", BASE_DIR / "netnotify.db"))
UDP_HOST = os.environ.get("NETNOTIFY_UDP_HOST", "0.0.0.0")
UDP_PORT = int(os.environ.get("NETNOTIFY_UDP_PORT", "9999"))
WEB_HOST = os.environ.get("NETNOTIFY_WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.environ.get("NETNOTIFY_WEB_PORT", "5000"))
ADMIN_PASSWORD = os.environ.get("NETNOTIFY_ADMIN_PASSWORD", "change-me-now")
MAX_MESSAGE_LENGTH = 500
MAX_PACKET_SIZE = 4096
HEARTBEAT_TIMEOUT = 35
MAX_RETRIES = 3
RETRY_INTERVAL = 2.0

app = Flask(__name__)
app.secret_key = os.environ.get("NETNOTIFY_SECRET_KEY") or secrets.token_hex(32)

clients_lock = threading.Lock()
clients = {}  # client_id -> {name, address, last_seen}
stop_event = threading.Event()
udp_socket = None
udp_thread = None
retry_thread = None


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_connect():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db_connect() as con:
        con.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL,
            severity TEXT NOT NULL, created_at TEXT NOT NULL, sender TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notification_id TEXT NOT NULL, client_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
            last_sent REAL, acked_at TEXT,
            UNIQUE(notification_id, client_id),
            FOREIGN KEY(notification_id) REFERENCES notifications(id)
        );
        CREATE INDEX IF NOT EXISTS idx_deliveries_status ON deliveries(status, last_sent);
        CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at);
        """)


def send_packet(address, payload):
    global udp_socket
    if not udp_socket:
        return False
    try:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if len(data) > MAX_PACKET_SIZE:
            return False
        udp_socket.sendto(data, address)
        return True
    except (OSError, ValueError):
        return False


def handle_datagram(data, address):
    if len(data) > MAX_PACKET_SIZE:
        return
    try:
        packet = json.loads(data.decode("utf-8"))
        if not isinstance(packet, dict):
            return
        kind = packet.get("type")
        client_id = str(packet.get("client_id", ""))[:80]
        if kind == "register":
            name = str(packet.get("name", "Unnamed client")).strip()[:50] or "Unnamed client"
            if not client_id:
                return
            with clients_lock:
                clients[client_id] = {"name": name, "address": address, "last_seen": time.time()}
            send_packet(address, {"type": "registered", "client_id": client_id, "server_time": utc_now()})
            print(f"[REGISTER] {name} ({address[0]}:{address[1]})")
        elif kind == "heartbeat":
            if not client_id:
                return
            with clients_lock:
                entry = clients.get(client_id)
                if entry:
                    entry["address"] = address
                    entry["last_seen"] = time.time()
        elif kind == "ack":
            notification_id = str(packet.get("notification_id", ""))[:80]
            if client_id and notification_id:
                with db_connect() as con:
                    con.execute("UPDATE deliveries SET status='delivered', acked_at=? WHERE notification_id=? AND client_id=?",
                                (utc_now(), notification_id, client_id))
        else:
            # Unknown packet types are intentionally ignored.
            return
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return


def udp_listener():
    while not stop_event.is_set():
        try:
            data, address = udp_socket.recvfrom(MAX_PACKET_SIZE + 1)
            handle_datagram(data, address)
        except socket.timeout:
            continue
        except OSError:
            if not stop_event.is_set():
                print("[UDP] Socket error; listener stopped.")
            break


def retry_worker():
    while not stop_event.wait(1.0):
        now = time.time()
        with db_connect() as con:
            rows = con.execute("""SELECT d.id, d.notification_id, d.client_id, d.attempts,
                                      n.title, n.body, n.severity, n.created_at
                               FROM deliveries d JOIN notifications n ON n.id=d.notification_id
                               WHERE d.status='pending' AND d.last_sent IS NOT NULL AND d.last_sent <= ?
                               ORDER BY d.id LIMIT 100""", (now - RETRY_INTERVAL,)).fetchall()
            for row in rows:
                if row["attempts"] >= MAX_RETRIES:
                    con.execute("UPDATE deliveries SET status='failed' WHERE id=?", (row["id"],))
                    continue
                with clients_lock:
                    client = clients.get(row["client_id"])
                    address = client["address"] if client else None
                if not address:
                    con.execute("UPDATE deliveries SET status='failed' WHERE id=?", (row["id"],))
                    continue
                packet = {"type": "notification", "notification_id": row["notification_id"],
                          "title": row["title"], "body": row["body"], "severity": row["severity"],
                          "created_at": row["created_at"], "attempt": row["attempts"] + 1}
                if send_packet(address, packet):
                    con.execute("UPDATE deliveries SET attempts=attempts+1, last_sent=? WHERE id=?", (now, row["id"]))
                else:
                    con.execute("UPDATE deliveries SET status='failed' WHERE id=?", (row["id"],))


def start_network():
    global udp_socket, udp_thread, retry_thread
    if udp_thread and udp_thread.is_alive():
        return
    stop_event.clear()
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_socket.settimeout(1.0)
    udp_socket.bind((UDP_HOST, UDP_PORT))
    udp_thread = threading.Thread(target=udp_listener, daemon=True, name="netnotify-udp")
    retry_thread = threading.Thread(target=retry_worker, daemon=True, name="netnotify-retry")
    udp_thread.start()
    retry_thread.start()
    print(f"[UDP] Listening on {UDP_HOST}:{UDP_PORT}")


def stop_network():
    stop_event.set()
    if udp_socket:
        try:
            udp_socket.close()
        except OSError:
            pass


def logged_in(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if secrets.compare_digest(password, ADMIN_PASSWORD):
            session.clear()
            session["authenticated"] = True
            return redirect(url_for("dashboard"))
        flash("Incorrect password. Please try again.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@logged_in
def dashboard():
    with db_connect() as con:
        total = con.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
        delivery_stats = {r["status"]: r["n"] for r in con.execute("SELECT status, COUNT(*) n FROM deliveries GROUP BY status")}
        history = con.execute("""SELECT n.*, COUNT(d.id) recipients,
            SUM(CASE WHEN d.status='delivered' THEN 1 ELSE 0 END) delivered,
            SUM(CASE WHEN d.status='failed' THEN 1 ELSE 0 END) failed
            FROM notifications n LEFT JOIN deliveries d ON d.notification_id=n.id
            GROUP BY n.id ORDER BY n.created_at DESC LIMIT 20""").fetchall()
    now = time.time()
    with clients_lock:
        client_rows = [{"client_id": cid, "name": c["name"], "ip": c["address"][0],
                        "port": c["address"][1], "online": now - c["last_seen"] < HEARTBEAT_TIMEOUT,
                        "last_seen": int(now - c["last_seen"])} for cid, c in clients.items()]
    client_rows.sort(key=lambda x: (not x["online"], x["name"].lower()))
    return render_template("dashboard.html", total=total, stats=delivery_stats,
                           history=history, clients=client_rows, udp_port=UDP_PORT)


@app.route("/send", methods=["POST"])
@logged_in
def send_notification():
    title = request.form.get("title", "").strip()
    body = request.form.get("body", "").strip()
    severity = request.form.get("severity", "INFO").upper()
    if not title or len(title) > 100:
        flash("Title is required and must be at most 100 characters.", "error")
        return redirect(url_for("dashboard"))
    if not body or len(body) > MAX_MESSAGE_LENGTH:
        flash(f"Message is required and must be at most {MAX_MESSAGE_LENGTH} characters.", "error")
        return redirect(url_for("dashboard"))
    if severity not in {"INFO", "WARNING", "CRITICAL"}:
        flash("Invalid severity category.", "error")
        return redirect(url_for("dashboard"))
    with clients_lock:
        recipients = [(cid, c["address"]) for cid, c in clients.items() if time.time() - c["last_seen"] < HEARTBEAT_TIMEOUT]
    if not recipients:
        flash("No active clients yet. Start a client and wait for it to register.", "error")
        return redirect(url_for("dashboard"))
    notification_id = str(uuid.uuid4())
    created_at = utc_now()
    with db_connect() as con:
        con.execute("INSERT INTO notifications(id,title,body,severity,created_at,sender) VALUES(?,?,?,?,?,?)",
                    (notification_id, title, body, severity, created_at, "Admin"))
        for client_id, _ in recipients:
            con.execute("INSERT INTO deliveries(notification_id,client_id,status,attempts,last_sent) VALUES(?,?, 'pending', 1, ?)",
                        (notification_id, client_id, time.time()))
    packet = {"type": "notification", "notification_id": notification_id, "title": title,
              "body": body, "severity": severity, "created_at": created_at, "attempt": 1}
    sent = 0
    for _, address in recipients:
        if send_packet(address, packet):
            sent += 1
    flash(f"Notification sent over UDP to {sent}/{len(recipients)} active client(s). Delivery status updates as acknowledgements arrive.", "success")
    return redirect(url_for("dashboard"))


@app.route("/api/status")
@logged_in
def api_status():
    now = time.time()
    with clients_lock:
        online = sum(1 for c in clients.values() if now - c["last_seen"] < HEARTBEAT_TIMEOUT)
    with db_connect() as con:
        counts = {r["status"]: r["n"] for r in con.execute("SELECT status, COUNT(*) n FROM deliveries GROUP BY status")}
    return jsonify({"udp_port": UDP_PORT, "online_clients": online, "delivery_status": counts, "time": utc_now()})


@app.errorhandler(413)
def too_large(_error):
    return "Request too large", 413


if __name__ == "__main__":
    init_db()
    start_network()
    try:
        print(f"[WEB] Open http://{WEB_HOST}:{WEB_PORT}")
        if ADMIN_PASSWORD == "change-me-now":
            print("[SECURITY] Default dashboard password is change-me-now. Set NETNOTIFY_ADMIN_PASSWORD before using on a LAN.")
        app.run(host=WEB_HOST, port=WEB_PORT, debug=False, threaded=True)
    finally:
        stop_network()
