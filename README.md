# NetNotify — UDP-Based Network Notification System

A Computer Networks project featuring a Flask admin dashboard, a Python UDP notification coordinator, multiple UDP clients, SQLite history, client heartbeats, delivery acknowledgements and bounded retries.

## Requirements
- Python 3.10+
- Flask (installed from `requirements.txt`)

## Quick start (Kali Linux / Ubuntu)

```bash
cd netnotify
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export NETNOTIFY_ADMIN_PASSWORD='choose-a-strong-demo-password'
python app.py
```

Open `http://127.0.0.1:5000` and log in with the password set above. The UDP service listens on port `9999` by default.

In a second terminal, from the project folder:

```bash
source .venv/bin/activate
python client.py --server 127.0.0.1 --name Lab-PC-1
```

Start another client in a third terminal:

```bash
source .venv/bin/activate
python client.py --server 127.0.0.1 --name Lab-PC-2
```

Send a notification from the dashboard and confirm that both terminals receive it. The client sends an ACK and the dashboard history updates on refresh.

## LAN demonstration
1. Run the server on the computer hosting NetNotify. To expose the dashboard to the LAN, set `NETNOTIFY_WEB_HOST=0.0.0.0`; keep a strong `NETNOTIFY_ADMIN_PASSWORD` and do not expose it to an untrusted network. The default dashboard bind is localhost-only.
2. Find the server's LAN IPv4 address using `ip -4 addr`.
3. Allow UDP port 9999 through the host firewall if enabled.
4. On another machine, install Python and Flask (or copy the project and create a venv), then run `python client.py --server SERVER_LAN_IP --name Laptop-2`.
5. If you expose the dashboard on the LAN, use `http://SERVER_LAN_IP:5000` and the configured admin password. Use only on a trusted LAN; use a reverse proxy with HTTPS for any wider exposure.

Environment variables:
- `NETNOTIFY_ADMIN_PASSWORD`: dashboard password (default demo password is `change-me-now`; change it before LAN use).
- `NETNOTIFY_SECRET_KEY`: stable Flask session secret (generated each run if omitted).
- `NETNOTIFY_WEB_HOST` / `NETNOTIFY_WEB_PORT`: web bind and port (defaults `127.0.0.1:5000`).
- `NETNOTIFY_UDP_HOST` / `NETNOTIFY_UDP_PORT`: UDP bind and port (defaults `0.0.0.0:9999`).
- `NETNOTIFY_DB`: optional SQLite database path.

## Architecture and protocol
- HTTP is used only between the browser and Flask dashboard.
- UDP carries compact JSON datagrams between the server and clients.
- Client packet types: `register`, `heartbeat`, `ack`.
- Server packet types: `registered`, `notification`.
- Client heartbeats refresh a client's last-seen time. The dashboard considers a client online for 35 seconds after its latest heartbeat.
- A notification is recorded in SQLite before being sent. Each client gets a delivery row. Clients ACK notification IDs; pending rows are retried up to a bounded number of times. Duplicate notification delivery is possible under UDP retry conditions; the client displays each received datagram and ACKs it.
- UDP itself does not guarantee delivery, ordering or duplicate suppression. Application-level ACK/retry improves observability but is not equivalent to a reliable transport protocol.

## Testing checklist
1. Log in with the configured password.
2. Start two clients; check both appear online.
3. Send INFO, WARNING and CRITICAL messages; confirm both clients display each one.
4. Confirm delivery counters update after ACKs arrive.
5. Stop one client and wait at least 35 seconds; it should become offline and will not be targeted by new broadcasts.
6. Enter a blank title or body; validation should reject it.
7. Send a message longer than 500 characters; browser validation prevents it and server-side validation also rejects it.
8. Restart the app; notification history should remain in `netnotify.db`.
9. Use Wireshark with filter `udp.port == 9999` to observe registration, notification and ACK datagrams.

## Limitations / security notes
- This is an academic LAN demo, not a production alerting platform.
- UDP payloads are not encrypted or authenticated. Use only on a trusted network; do not send secrets.
- The Flask dashboard has a password-protected session, but should not be exposed directly to the public internet.
- Client registration uses a client-supplied ID and is intended for a controlled lab. A production version should authenticate clients, protect against spoofing/replay, add TLS for web traffic, rate-limit input, and use a robust message broker or reliable transport where required.
# netnotify
