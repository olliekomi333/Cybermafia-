import socket
import threading
import json
import random
import time
from db_helper import DBHelper

HOST = '0.0.0.0'
PORT = 5555

DEFAULT_SETTINGS = {"size": 6, "killers": 1, "detectives": 1, "quests": 3}
BOT_QUEST_SECONDS = 5        # сколько бот "выполняет" задание
BOT_THINK_RANGE = (2, 5)     # пауза между заданиями бота (сек)
# номер комнаты: вместимость
# 1 - башня, 2 - центр, 3 - правая, 4 - терраса, 5 - нижняя
QUEST_ROOMS = {1: 2, 2: 2, 3: 2, 4: 1, 5: 1}

ROUND_SECONDS = 60   # длина раунда (для проверки детектива)


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
        threading.Thread(target=self.bot_loop, daemon=True).start()

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

    @staticmethod
    def current_round(lobby):
        elapsed = time.time() - lobby["round_start"]
        return int(elapsed // ROUND_SECONDS) + 1, ROUND_SECONDS - int(elapsed % ROUND_SECONDS)

    @staticmethod
    @staticmethod
    def participants(lobby):
        """Люди + боты (боты появляются после старта)."""
        return list(lobby["players"]) + list(lobby.get("bots", []))

    @staticmethod
    def check_win(lobby):
        if not lobby.get("started") or lobby.get("winner"):
            return
        roles = lobby.get("roles", {})
        done = lobby.get("done", {})
        peace = [p for p in CyberServer.participants(lobby) if roles.get(p) != "killer"]
        total = len(peace) * lobby["quests"]
        if total > 0 and sum(len(done.get(p, [])) for p in peace) >= total:
            lobby["winner"] = "peaceful"
            print("[GAME] Мирные победили!")
    def lobby_state(self, code, lobby, user):
        self.check_win(lobby)
        started = lobby.get("started", False)
        humans = lobby["players"]
        roles = lobby.get("roles", {})
        done = lobby.get("done", {})

        slots = [{"name": n, "bot": False, "host": n == lobby["host"]} for n in humans]
        if started:
            bots = lobby.get("bots", [])
        else:
            bots = [f"Bot {i + 1}" for i in range(lobby["size"] - len(humans))]
        for b in bots:
            slots.append({"name": b, "bot": True, "host": False})

        # было: peace = [p for p in humans if roles.get(p) != "killer"]
        peace = [p for p in self.participants(lobby) if roles.get(p) != "killer"]
        progress = {
            "done": sum(len(done.get(p, [])) for p in peace),
            "total": len(peace) * lobby["quests"],
        }

        my_role = roles.get(user)
        state = {
            "code": code,
            "host": lobby["host"],
            "size": lobby["size"],
            "killers": lobby["killers"],
            "detectives": lobby["detectives"],
            "quests": lobby["quests"],
            "started": started,
            "rooms": [
                {"id": r, "cap": cap, "players": list(lobby.get("rooms", {}).get(r, []))}
                for r, cap in QUEST_ROOMS.items()
            ],
            "my_done": list(done.get(user, [])),
            "progress": progress,
            "slots": slots,
            "my_role": my_role,
            "winner": lobby.get("winner"),
        }

        if started:
            rnd, left = self.current_round(lobby)
            state["round"] = rnd
            state["round_left"] = left
            if my_role == "killer":
                state["teammates"] = [n for n, r in roles.items()
                                      if r == "killer" and n != user]
            if my_role == "detective":
                checks = lobby.get("checks", {}).get(user, [])
                state["checks"] = list(checks)
                state["can_check"] = not any(c["round"] == rnd for c in checks)
            if lobby.get("winner"):
                state["reveal"] = dict(roles)
        return state

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
        for plist in lobby.get("rooms", {}).values():
            if username in plist:
                plist.remove(username)
        lobby.get("done", {}).pop(username, None)
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

        if action == "guest":
            with self.lobby_lock:
                if not user:
                    while True:
                        name = f"Guest{random.randint(100, 999)}"
                        if name not in self.clients:
                            break
                    session["username"] = name
                    self.clients[name] = conn
            return {"status": True, "username": session["username"]}

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
                return {"status": True,
                        "lobby": self.lobby_state(code, self.lobbies[code], user)}

        if action == "join_lobby":
            code = str(msg.get("code", "")).strip()
            with self.lobby_lock:
                lobby = self.lobbies.get(code)
                if not lobby:
                    return {"status": False, "msg": "Лобби не найдено!"}
                if user not in lobby["players"]:
                    if lobby.get("started"):
                        return {"status": False, "msg": "Игра уже началась!"}
                    if len(lobby["players"]) >= lobby["size"]:
                        return {"status": False, "msg": "Лобби заполнено!"}
                    self.leave_lobby(user)
                    lobby["players"].append(user)
                    print(f"[LOBBY] {user} зашёл в лобби {code}")
                return {"status": True, "lobby": self.lobby_state(code, lobby, user)}

        if action == "get_lobby":
            with self.lobby_lock:
                code, lobby = self.find_lobby(user)
                if not lobby:
                    return {"status": False, "closed": True, "msg": "Вы больше не в лобби"}
                return {"status": True, "lobby": self.lobby_state(code, lobby, user)}

        if action == "leave_lobby":
            with self.lobby_lock:
                self.leave_lobby(user)
            return {"status": True}

        if action == "start_game":
            with self.lobby_lock:
                code, lobby = self.find_lobby(user)
                if not lobby:
                    return {"status": False, "closed": True, "msg": "Вы не в лобби"}
                if lobby["host"] != user:
                    return {"status": False, "msg": "Только хост может начать!"}
                if not lobby.get("started"):
                    humans = list(lobby["players"])
                    bots = [f"Bot {i + 1}" for i in range(lobby["size"] - len(humans))]
                    names = humans + bots
                    random.shuffle(names)
                    k, d = lobby["killers"], lobby["detectives"]
                    roles = {}
                    for i, n in enumerate(names):
                        if i < k:
                            roles[n] = "killer"
                        elif i < k + d:
                            roles[n] = "detective"
                        else:
                            roles[n] = "peaceful"
                    lobby.update(started=True, bots=bots, roles=roles,
                                 done={p: [] for p in names},  # было: humans
                                 round_start=time.time(), checks={},
                                 bot_state={b: {"room": None,
                                                "next_at": time.time() + random.uniform(*BOT_THINK_RANGE)}
                                            for b in bots})
                    print(f"[LOBBY] {user} запустил игру в лобби {code}")
                    print(f"[ROLES] {roles}")
                return {"status": True, "lobby": self.lobby_state(code, lobby, user)}

        if action in ("enter_room", "exit_room"):
            with self.lobby_lock:
                code, lobby = self.find_lobby(user)
                if not lobby:
                    return {"status": False, "closed": True, "msg": "Вы не в лобби"}
                rooms = lobby.setdefault("rooms", {})
                rid = None
                if action == "enter_room":
                    if lobby.get("winner"):
                        return {"status": False, "msg": "Игра окончена!"}
                    rid = int(msg.get("room", -1))
                    if rid not in QUEST_ROOMS:
                        return {"status": False, "msg": "Нет такой комнаты"}
                    mine = lobby.get("done", {}).get(user, [])
                    if rid in mine:
                        return {"status": False, "msg": "Вы уже выполнили здесь задание!"}
                    if len(mine) >= lobby["quests"]:
                        return {"status": False, "msg": "Вы выполнили все свои задания!"}
                    others = [p for p in rooms.get(rid, []) if p != user]
                    if len(others) >= QUEST_ROOMS[rid]:
                        return {"status": False, "msg": "Комната занята!"}
                for plist in rooms.values():
                    if user in plist:
                        plist.remove(user)
                if rid is not None:
                    rooms.setdefault(rid, []).append(user)
                return {"status": True, "lobby": self.lobby_state(code, lobby, user)}

        if action == "complete_quest":
            with self.lobby_lock:
                code, lobby = self.find_lobby(user)
                if not lobby:
                    return {"status": False, "closed": True, "msg": "Вы не в лобби"}
                if lobby.get("winner"):
                    return {"status": False, "msg": "Игра окончена!"}
                rid = int(msg.get("room", -1))
                if user not in lobby.get("rooms", {}).get(rid, []):
                    return {"status": False, "msg": "Вы не в этой комнате!"}
                mine = lobby.setdefault("done", {}).setdefault(user, [])
                if rid not in mine and len(mine) < lobby["quests"]:
                    mine.append(rid)
                    print(f"[QUEST] {user} выполнил задание в комнате {rid}")
                return {"status": True, "lobby": self.lobby_state(code, lobby, user)}

        if action == "check_player":
            with self.lobby_lock:
                code, lobby = self.find_lobby(user)
                if not lobby or not lobby.get("started"):
                    return {"status": False, "closed": not lobby, "msg": "Игра не идёт"}
                if lobby.get("winner"):
                    return {"status": False, "msg": "Игра окончена!"}
                roles = lobby["roles"]
                if roles.get(user) != "detective":
                    return {"status": False, "msg": "Вы не детектив!"}
                target = str(msg.get("target", ""))
                if target == user or target not in roles:
                    return {"status": False, "msg": "Нельзя проверить этого игрока"}
                rnd, _ = self.current_round(lobby)
                checks = lobby.setdefault("checks", {}).setdefault(user, [])
                if any(c["round"] == rnd for c in checks):
                    return {"status": False, "msg": "В этом раунде проверка уже использована!"}
                checks.append({"round": rnd, "target": target,
                               "deviant": roles[target] == "killer"})
                print(f"[CHECK] {user} проверил {target} (раунд {rnd})")
                return {"status": True, "lobby": self.lobby_state(code, lobby, user)}

        if action == "update_settings":
            with self.lobby_lock:
                code, lobby = self.find_lobby(user)
                if not lobby:
                    return {"status": False, "closed": True, "msg": "Вы не в лобби"}
                if lobby["host"] != user:
                    return {"status": False, "msg": "Только хост может менять настройки!"}
                if lobby.get("started"):
                    return {"status": False, "msg": "Игра уже началась!"}

                size = int(msg.get("size", lobby["size"]))
                killers = int(msg.get("killers", lobby["killers"]))
                detectives = int(msg.get("detectives", lobby["detectives"]))
                quests = int(msg.get("quests", lobby["quests"]))

                if size not in (6, 8):
                    return {"status": False, "msg": "Игроков может быть 6 или 8"}
                if len(lobby["players"]) > size:
                    return {"status": False, "msg": f"В лобби уже больше {size} игроков"}
                if not 1 <= killers <= 2:
                    return {"status": False, "msg": "Убийц: от 1 до 2"}
                if not 1 <= detectives <= 2:
                    return {"status": False, "msg": "Детективов: от 1 до 2"}
                if not 1 <= quests <= 5:
                    return {"status": False, "msg": "Квестов: от 1 до 5"}

                lobby.update(size=size, killers=killers, detectives=detectives, quests=quests)
                return {"status": True, "lobby": self.lobby_state(code, lobby, user)}

        return {"status": False, "msg": "Неизвестное действие"}

    def bot_tick(self):
        now = time.time()
        with self.lobby_lock:
            for lobby in list(self.lobbies.values()):
                if not lobby.get("started") or lobby.get("winner"):
                    continue
                rooms = lobby.setdefault("rooms", {})
                done = lobby.setdefault("done", {})
                for bot, st in lobby.get("bot_state", {}).items():
                    if now < st["next_at"]:
                        continue

                    rid = st["room"]
                    if rid is not None:
                        # прошло 5 секунд -> "complete_quest" + освободить комнату
                        if bot in rooms.get(rid, []):
                            rooms[rid].remove(bot)
                        mine = done.setdefault(bot, [])
                        if rid not in mine and len(mine) < lobby["quests"]:
                            mine.append(rid)
                            print(f"[BOT QUEST] {bot} выполнил задание в комнате {rid}")
                        st["room"] = None
                        st["next_at"] = now + random.uniform(*BOT_THINK_RANGE)
                        self.check_win(lobby)
                        if lobby.get("winner"):
                            break
                        continue

                    # бот свободен -> ищем пустую комнату 0/1, где он ещё не был
                    mine = done.setdefault(bot, [])
                    if len(mine) >= lobby["quests"]:
                        continue
                    free = [r for r, cap in QUEST_ROOMS.items()
                            if cap == 1 and r not in mine and not rooms.get(r)]
                    if not free:
                        continue
                    rid = random.choice(free)
                    rooms.setdefault(rid, []).append(bot)  # "замок" комнаты
                    st["room"] = rid
                    st["next_at"] = now + BOT_QUEST_SECONDS

    def bot_loop(self):
        while True:
            time.sleep(1)
            try:
                self.bot_tick()
            except Exception as e:
                print(f"[BOT ERROR] {e}")

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