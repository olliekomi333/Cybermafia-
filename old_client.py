import socket
import json


class TcpClient:
    def __init__(self, host="127.0.0.1", port=5000):
        self.host = host
        self.port = port
        self.sock = None
        self.buffer = ""

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def send(self, data: dict) -> dict:
        """
        Send JSON request and wait for JSON response.
        """

        message = json.dumps(data) + "\n"
        self.sock.sendall(message.encode("utf-8"))

        # while True:
        #     chunk = self.sock.recv(4096)
        #
        #     if not chunk:
        #         raise ConnectionError("Server disconnected")
        #
        #     self.buffer += chunk.decode("utf-8")
        #
        #     if "\n" in self.buffer:
        #         line, self.buffer = self.buffer.split("\n", 1)
        #
        #         if line.strip():
        #             return json.loads(line)

    def register(self, username: str, password: str) -> dict:
        return self.send({
            "action": "register",
            "username": username,
            "password": password
        })

    def login(self, username: str, password: str) -> dict:
        return self.send({
            "action": "login",
            "username": username,
            "password": password
        })

    def create_room(self) -> dict:
        return self.send({
            "action": "create_room"
        })


if __name__ == "__main__":
    client = TcpClient()
    client.connect()

    try:
        # print("REGISTER")
        # print(client.register("alice", "secret123"))

        print("LOGIN")
        print(client.login("alice", "secret123"))


        # print("CREATE ROOM")
        # print(client.create_room())

    finally:
        client.close()