import socket
import threading
import json

import db_helper

HOST = "0.0.0.0"
PORT = 5000


def send_json(conn, data):
    message = json.dumps(data) + "\n"
    conn.sendall(message.encode("utf-8"))


def handle_client(conn, addr):
    print(f"[CONNECTED] {addr}")

    buffer = ""

    try:
        while True:
            data = conn.recv(4096)


            try:
                message = json.loads(data)

                print(f"[{addr}] Received:", message)

                response = {
                    "status": "ok",
                    "received": message
                }

                if message["action"] == "register":
                    db_helper.register_user(message["username"], message["password"])

                # send_json(conn, response)

            except json.JSONDecodeError as e:
                send_json(conn, {
                    "status": "error",
                    "message": f"Invalid JSON: {e}"
                    })

    except Exception as e:
        print(f"[ERROR] {addr}: {e}")

    finally:
        conn.close()
        print(f"[DISCONNECTED] {addr}")


def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Allow immediate reuse after restart
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server.bind((HOST, PORT))
    server.listen()

    print(f"Server listening on {HOST}:{PORT}")

    while True:
        conn, addr = server.accept()

        client_thread = threading.Thread(
            target=handle_client,
            args=(conn, addr),
            daemon=True
        )
        client_thread.start()


if __name__ == "__main__":
    start_server()