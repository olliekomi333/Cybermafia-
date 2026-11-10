import socket
import threading
import json
import random
from db_helper import DBHelper

HOST = '127.0.0.1'
PORT = 5555

DEFAULT_SETTINGS = {"size": 6, "killers": 1, "detectives": 1, "quests": 3}


class CyberServer:
    def __init__(self):
        self.db = DBHelper()
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((HOST, PORT))
        self.server.listen()
        self.clients = {}          # username -> conn
        self.lobbies = {}          # code -> dict
        self.lobby_lock = threading.Lock()
        print(f"[SERVER STARTED] Сервер запущен на {HOST}:{PORT}...")

    # ---------- вспомогательное ----------
    @staticmethod
    def send(conn, payload):
        conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))

    def new_code(self):
        """Случайный код, которого нет среди текущих лобби (вызывать под lock)."""
        while True:
            code = str(random.randint(1000, 9999))
            if code not in self.lobbies:
                return code

    def lobby_state(self, code, lobby):
        humans = lobby["players"]
        slots = [{"name": n, "bot": False, "host": n == lobby["host"]} for n in humans]
        for i in range(lobby["size"] - len(humans)):
            slots.append({"name": f"Bot {i + 1}", "bot": True, "host": False})
        return {
            "code": code,
            "host": lobby["host"],
            "size": lobby["size"],
            "killers": lobby["killers"],
            "detectives": lobby["detectives"],
            "quests": lobby["quests"],
            "slots": slots,
        }

    def find_lobby(self, username):
        for code, lobby in self.lobbies.items():
            if username in lobby["players"]:
                return code, lobby
        return None, None

    def leave_lobby(self, username):
        """Убрать игрока из его лобби (вызывать под lock)."""
        code, lobby = self.find_lobby(username)
        if not lobby:
            return
        lobby["players"].remove(username)
        if not lobby["players"]:
            del self.lobbies[code]
        elif lobby["host"] == username:
            lobby["host"] = lobby["players"][0]

    # ---------- обработка запросов ----------
    def process(self, msg, session, conn):
        action = msg.get("action")
        user = session["username"]

        if action == "login":
            name = str(msg.get("username", "")).strip()[:12]
            pwd = str(msg.get("password", ""))
            if not name:
                return {"status": False, "msg": "Введите имя!"}
            with self.lobby_lock:
                if name in self.clients and self.clients[name] is not conn:
                    return {"status": False, "msg": "Этот аккаунт уже в игре!"}
            success, skin, resp_msg = self.db.register_or_login(name, pwd)
            if success:
                with self.lobby_lock:
                    if user and user != name:
                        self.leave_lobby(user)
                        self.clients.pop(user, None)
                    session["username"] = name
                    self.clients[name] = conn
            return {"status": success, "msg": resp_msg, "skin": skin, "username": name}

        if not user:
            return {"status": False, "msg": "Сначала войдите в аккаунт!"}

        if action == "update_skin":
            self.db.update_skin(user, msg["skin"])
            return {"status": True}

        if action == "create_lobby":
            with self.lobby_lock:
                self.leave_lobby(user)
                code = self.new_code()
                self.lobbies[code] = {"host": user, "players": [user], **DEFAULT_SETTINGS}
                print(f"[LOBBY] {user} создал лобби {code}")
                return {"status": True, "lobby": self.lobby_state(code, self.lobbies[code])}

        if action == "join_lobby":
            code = str(msg.get("code", "")).strip()
            with self.lobby_lock:
                lobby = self.lobbies.get(code)
                if not lobby:
                    return {"status": False, "msg": "Лобби не найдено!"}
                if user not in lobby["players"]:
                    if len(lobby["players"]) >= lobby["size"]:
                        return {"status": False, "msg": "Лобби заполнено!"}
                    self.leave_lobby(user)
                    lobby["players"].append(user)
                    print(f"[LOBBY] {user} зашёл в лобби {code}")
                return {"status": True, "lobby": self.lobby_state(code, lobby)}

        if action == "get_lobby":
            with self.lobby_lock:
                code, lobby = self.find_lobby(user)
                if not lobby:
                    return {"status": False, "closed": True, "msg": "Вы больше не в лобби"}
                return {"status": True, "lobby": self.lobby_state(code, lobby)}

        if action == "leave_lobby":
            with self.lobby_lock:
                self.leave_lobby(user)
            return {"status": True}

        if action == "update_settings":
            with self.lobby_lock:
                code, lobby = self.find_lobby(user)
                if not lobby:
                    return {"status": False, "closed": True, "msg": "Вы не в лобби"}
                if lobby["host"] != user:
                    return {"status": False, "msg": "Только хост может менять настройки!"}

                size = int(msg.get("size", lobby["size"]))
                killers = int(msg.get("killers", lobby["killers"]))
                detectives = int(msg.get("detectives", lobby["detectives"]))
                quests = int(msg.get("quests", lobby["quests"]))

                if size not in (6, 8):
                    return {"status": False, "msg": "Игроков может быть 6 или 8"}
                if len(lobby["players"]) > size:
                    return {"status": False, "msg": f"В лобби уже больше {size} игроков"}

                max_killers = size // 2 - 1
                if size != lobby["size"]:
                    killers = min(killers, max_killers)  # при смене размера подгоняем
                if not 1 <= killers <= max_killers:
                    return {"status": False, "msg": f"Убийц: от 1 до {max_killers}"}
                if not 0 <= detectives <= 2:
                    return {"status": False, "msg": "Детективов: от 0 до 2"}
                if not 1 <= quests <= 5:
                    return {"status": False, "msg": "Квестов: от 1 до 5"}

                lobby.update(size=size, killers=killers, detectives=detectives, quests=quests)
                return {"status": True, "lobby": self.lobby_state(code, lobby)}

        return {"status": False, "msg": "Неизвестное действие"}

    # ---------- клиенты ----------
    def handle_client(self, conn, addr):
        print(f"[NEW CONNECTION] {addr} подключился.")
        session = {"username": None}
        buf = b""
        try:
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                        resp = self.process(msg, session, conn)
                    except Exception as e:
                        print(f"[ERROR] Запрос от {addr}: {e}")
                        resp = {"status": False, "msg": "Ошибка сервера"}
                    self.send(conn, resp)
        except Exception as e:
            print(f"[ERROR] Ошибка с клиентом {addr}: {e}")
        finally:
            username = session["username"]
            with self.lobby_lock:
                if username:
                    self.leave_lobby(username)
                    if self.clients.get(username) is conn:
                        del self.clients[username]
            conn.close()
            print(f"[DISCONNECTED] Клиент {addr} отключился.")

    def run(self):
        while True:
            conn, addr = self.server.accept()
            thread = threading.Thread(target=self.handle_client, args=(conn, addr))
            thread.daemon = True
            thread.start()


if __name__ == "__main__":
    server = CyberServer()
    server.run()