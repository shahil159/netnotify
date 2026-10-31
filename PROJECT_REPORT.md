# NetNotify: UDP-Based Network Notification System

## Abstract
NetNotify is a lightweight network notification system that distributes short announcements from an administrator to registered clients over User Datagram Protocol (UDP). A Flask-based web dashboard provides a user-friendly interface for composing messages and monitoring clients. A Python UDP service handles registration, heartbeat messages, notification datagrams and acknowledgements. SQLite records notification history and per-client delivery outcomes. Application-level acknowledgement and bounded retry logic improve delivery visibility while illustrating that UDP itself does not guarantee delivery.

## Problem statement
In a local lab or small network, administrators may need to send concise announcements to multiple active computers without requiring each client to continuously poll a web page. NetNotify demonstrates a simple client-server design using UDP datagrams and a web-based control interface.

## Objectives
1. Implement a UDP server and multiple UDP clients.
2. Distribute INFO, WARNING and CRITICAL notifications.
3. Track active clients using registration and heartbeat messages.
4. Record messages and delivery status in SQLite.
5. Implement acknowledgements and bounded retries at the application layer.
6. Provide a dashboard and test the system using local clients and optionally a LAN.

## System architecture
The administrator's browser communicates with the Flask web application over HTTP. The web application stores notifications in SQLite and asks the UDP coordinator to send JSON datagrams to active clients. Clients return heartbeat and acknowledgement datagrams to the UDP coordinator. The coordinator updates in-memory client status and persistent delivery records.

## Modules
- **Web dashboard:** authentication, message form, severity selector, client list, history and counters.
- **UDP coordinator:** binds to a UDP port, parses JSON, handles registration/heartbeat/ACK messages, and sends notifications.
- **UDP client:** registers itself, sends periodic heartbeats, prints received messages, and acknowledges message IDs.
- **SQLite persistence:** stores notifications and per-client delivery attempts/status.
- **Retry worker:** retries pending deliveries after a timeout up to a configured bound.

## Protocol design
Messages are UTF-8 JSON objects. A registration packet includes `type`, `client_id` and `name`. A heartbeat includes `type` and `client_id`. A notification includes `type`, `notification_id`, `title`, `body`, `severity`, `created_at` and `attempt`. An acknowledgement includes `type`, `client_id` and `notification_id`. The receiver checks packet size and basic JSON structure before processing.

## Why UDP?
UDP is connectionless and has a small header/low protocol overhead. It is useful for demonstrating lightweight datagram messaging. However, it does not guarantee delivery, ordering or duplicate protection. NetNotify demonstrates application-level acknowledgements and retries to expose delivery status; this does not turn UDP into a fully reliable transport protocol.

## Test cases
| Test | Procedure | Expected result |
|---|---|---|
| T1 | Start the server | Web dashboard and UDP listener start |
| T2 | Start two clients | Both register and appear online |
| T3 | Send an INFO notification | Both active clients print the notification |
| T4 | Send WARNING and CRITICAL | Severity labels are displayed correctly |
| T5 | Receive ACKs | Delivery status changes to delivered |
| T6 | Stop a client | It is marked offline after the heartbeat timeout |
| T7 | Submit blank or oversized fields | Input validation rejects invalid content |
| T8 | Restart the server | Saved notification history remains in SQLite |
| T9 | Inspect traffic with Wireshark | UDP datagrams are visible on port 9999 |

## Security and limitations
The project is intended for a controlled academic lab. UDP data is unencrypted and the demo client identity is not cryptographically authenticated. The dashboard should remain bound to localhost unless a trusted-LAN demonstration is needed. A production deployment would require stronger client authentication, replay protection, TLS for the web UI, rate limiting, monitoring and deployment hardening.

## Conclusion
NetNotify demonstrates practical computer-networking concepts including UDP sockets, IP addresses and ports, datagram-based communication, client-server architecture, heartbeats, application-level acknowledgements, retries, and network packet inspection. It combines these concepts with a web dashboard and persistent event history to form an end-to-end academic project.

## Future scope
- Signed/authenticated client packets and replay protection.
- TLS-protected dashboard deployment.
- Targeted notifications and client groups.
- Desktop/system-tray alerts.
- Exportable audit logs and analytics.
- More robust reliability semantics and integration tests.
