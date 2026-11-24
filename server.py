import socket
import threading
import json
import random
import time
from collections import Counter
from db_helper import DBHelper

HOST = '127.0.0.1'
PORT = 5555

DEFAULT_SETTINGS = {"size": 6, "killers": 1, "detectives": 1, "quests": 3}

# номер комнаты: вместимость
QUEST_ROOMS = {1: 2, 2: 2, 3: 2, 4: 1, 5: 1}
ROOM_NAMES = {1: "Tower", 2: "Center", 3: "East wing", 4: "Terrace", 5: "South wing"}

ROUND_SECONDS = 60      # длина раунда (в конце раунда автоматически голосование)
MEETING_SECONDS = 60    # время на голосование
RESULT_SECONDS = 6      # сколько показывается итог голосования
CHAT_MAX_LEN = 80


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

    @staticmethod
    def peace_progress(lobby):
        """(сделано, всего) по заданиям мирных людей.
        У выбывших в 'всего' остаётся только то, что они уже сделали."""
        roles = lobby.get("roles", {})
        done = lobby.get("done", {})
        dead = lobby.get("dead", set())
        d = t = 0
        for p in lobby["players"]:
            if roles.get(p) == "killer":
                continue
            n = len(done.get(p, []))
            d += n
            t += n if p in dead else lobby["quests"]
        return d, t

    def check_win(self, lobby):
        if not lobby.get("started") or lobby.get("winner") or lobby.get("meeting"):
            return
        roles = lobby.get("roles", {})
        dead = lobby.get("dead", set())

        killers = [n for n, r in roles.items() if r == "killer"]
        if killers and all(k in dead for k in killers):
            lobby["winner"] = "peaceful"
            lobby["win_reason"] = "All deviants were ejected."
            print("[GAME] Мирные победили (все девианты выгнаны)!")
            return

        d, t = self.peace_progress(lobby)
        alive_peace = [p for p in lobby["players"]
                       if roles.get(p) != "killer" and p not in dead]
        if alive_peace and t > 0 and d >= t:
            lobby["winner"] = "peaceful"
            lobby["win_reason"] = "All tasks are complete."
            print("[GAME] Мирные победили (все задания выполнены)!")

    def start_meeting(self, lobby, reporter=None, room=None):
        """Начать голосование: по репорту тела (reporter) или по концу раунда (None)."""
        rooms = lobby.setdefault("rooms", {})
        names = [b["name"] for b in lobby.get("bodies", [])]
        lobby["known_dead"].update(names)
        lobby["bodies"] = []
        for pl in rooms.values():
            pl.clear()

        if reporter:
            text = (f"{reporter} found a body in the {ROOM_NAMES[room]}. "
                    f"Victims: {', '.join(names)}.")
        elif names:
            text = f"The round is over. Victims: {', '.join(names)}."
        else:
            text = "The round is over. Nobody was found dead."

        lobby["meeting"] = {
            "phase": "vote", "start": time.time(), "reporter": reporter,
            "room": room, "votes": {},
            "chat": [{"name": "SYSTEM", "text": text}],
        }

    def resolve_meeting(self, lobby):
        m = lobby["meeting"]
        counts = Counter(m["votes"].values())
        ejected = None
        if counts:
            top = counts.most_common()
            best_name, best_n = top[0]
            tie = len(top) > 1 and top[1][1] == best_n
            if best_name != "SKIP" and not tie:
                ejected = best_name
        was_deviant = False
        if ejected:
            lobby["dead"].add(ejected)
            lobby["known_dead"].add(ejected)
            was_deviant = lobby["roles"].get(ejected) == "killer"
        m["phase"] = "result"
        m["result_until"] = time.time() + RESULT_SECONDS
        m["result"] = {"ejected": ejected, "deviant": was_deviant, "tally": dict(counts)}
        print(f"[MEETING] Выгнан: {ejected} (девиант: {was_deviant})")

    def tick(self, lobby):
        """Обновляем таймеры раунда и голосования."""
        if not lobby.get("started") or lobby.get("winner"):
            return
        now = time.time()
        m = lobby.get("meeting")
        if m:
            if m["phase"] == "vote":
                voters = [p for p in lobby["players"] if p not in lobby["dead"]]
                everyone = bool(voters) and all(p in m["votes"] for p in voters)
                if everyone or now - m["start"] >= MEETING_SECONDS:
                    self.resolve_meeting(lobby)
            elif now >= m["result_until"]:
                lobby["meeting"] = None
                lobby["round"] += 1
                lobby["round_start"] = now
            return
        # раунд закончился по времени -> автоматическое голосование
        if now - lobby["round_start"] >= ROUND_SECONDS:
            self.start_meeting(lobby, None)
            print(f"[MEETING] Раунд {lobby['round']} закончился по времени")

    def lobby_state(self, code, lobby, user):
        self.tick(lobby)
        self.check_win(lobby)

        started = lobby.get("started", False)
        humans = lobby["players"]
        roles = lobby.get("roles", {})
        done = lobby.get("done", {})
        dead = lobby.get("dead", set())
        known = lobby.get("known_dead", set())
        my_role = roles.get(user)
        i_dead = user in dead
        sees_all = i_dead or my_role == "killer"
        shown_dead = dead if sees_all else known

        if started:
            bots = lobby.get("bots", [])
        else:
            bots = [f"Bot {i + 1}" for i in range(lobby["size"] - len(humans))]
        slots = [{"name": n, "bot": False, "host": n == lobby["host"],
                  "dead": n in shown_dead} for n in humans]
        slots += [{"name": b, "bot": True, "host": False,
                   "dead": b in shown_dead} for b in bots]

        d, t = self.peace_progress(lobby)
        rooms = lobby.get("rooms", {})
        bodies = lobby.get("bodies", [])
        # тело видит только тот, кто сейчас находится в этой комнате
        body_rooms = [r for r, pl in rooms.items()
                      if user in pl and any(b["room"] == r for b in bodies)]

        state = {
            "code": code,
            "host": lobby["host"],
            "size": lobby["size"],
            "killers": lobby["killers"],
            "detectives": lobby["detectives"],
            "quests": lobby["quests"],
            "started": started,
            "rooms": [
                {"id": r, "cap": cap, "players": list(rooms.get(r, []))}
                for r, cap in QUEST_ROOMS.items()
            ],
            "my_done": list(done.get(user, [])),
            "progress": {"done": d, "total": t},
            "slots": slots,
            "my_role": my_role,
            "alive": not i_dead,
            "body_rooms": body_rooms,
            "winner": lobby.get("winner"),
            "win_reason": lobby.get("win_reason", ""),
        }

        if started:
            now = time.time()
            state["round"] = lobby["round"]
            state["round_left"] = max(0, ROUND_SECONDS - int(now - lobby["round_start"]))
            if my_role == "killer":
                state["teammates"] = [n for n, r in roles.items()
                                      if r == "killer" and n != user]
                state["can_kill"] = (not i_dead and
                                     lobby["kills"].get(user) != lobby["round"])
            if my_role == "detective":
                checks = lobby.get("checks", {}).get(user, [])
                state["checks"] = list(checks)
                state["can_check"] = (not i_dead and not lobby.get("meeting") and
                                      not any(c["round"] == lobby["round"] for c in checks))
            if lobby.get("winner"):
                state["reveal"] = dict(roles)

            m = lobby.get("meeting")
            if m:
                cands = [n for n in humans + bots if n not in dead and n != user]
                ms = {
                    "phase": m["phase"],
                    "reporter": m["reporter"],
                    "candidates": cands,
                    "my_vote": m["votes"].get(user),
                    "voted": sorted(m["votes"].keys()),
                    "chat": m["chat"][-40:],
                    "can_vote": (not i_dead) and user in humans and user not in m["votes"],
                    "left": int(max(0, MEETING_SECONDS - (now - m["start"]))),
                }
                if m["phase"] == "result":
                    ms["result"] = m["result"]
                    ms["left"] = int(max(0, m["result_until"] - now))
                state["meeting"] = ms
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
                                 done={p: [] for p in humans},
                                 rooms={}, checks={}, kills={},
                                 dead=set(), known_dead=set(), bodies=[],
                                 meeting=None, round=1, round_start=time.time())
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
                    if lobby.get("meeting"):
                        return {"status": False, "msg": "Идёт голосование!"}
                    if user in lobby.get("dead", set()):
                        return {"status": False, "msg": "Вы выбыли из игры!"}
                    rid = int(msg.get("room", -1))
                    if rid not in QUEST_ROOMS:
                        return {"status": False, "msg": "Нет такой комнаты"}
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
                if lobby.get("winner") or lobby.get("meeting"):
                    return {"status": False, "msg": "Сейчас нельзя!"}
                if user in lobby.get("dead", set()):
                    return {"status": False, "msg": "Вы выбыли из игры!"}
                rid = int(msg.get("room", -1))
                if user not in lobby.get("rooms", {}).get(rid, []):
                    return {"status": False, "msg": "Вы не в этой комнате!"}
                mine = lobby.setdefault("done", {}).setdefault(user, [])
                if rid not in mine and len(mine) < lobby["quests"]:
                    mine.append(rid)
                    print(f"[QUEST] {user} выполнил задание в комнате {rid}")
                return {"status": True, "lobby": self.lobby_state(code, lobby, user)}

        if action == "kill":
            with self.lobby_lock:
                code, lobby = self.find_lobby(user)
                if not lobby or not lobby.get("started"):
                    return {"status": False, "msg": "Игра не идёт"}
                if lobby.get("winner") or lobby.get("meeting"):
                    return {"status": False, "msg": "Сейчас нельзя!"}
                roles = lobby["roles"]
                if roles.get(user) != "killer" or user in lobby["dead"]:
                    return {"status": False, "msg": "Вы не можете убивать!"}
                rid = int(msg.get("room", -1))
                target = str(msg.get("target", ""))
                rooms = lobby.setdefault("rooms", {})
                if rid not in QUEST_ROOMS or target == user or target not in rooms.get(rid, []):
                    return {"status": False, "msg": "Цели нет в этой комнате!"}
                if roles.get(target) == "killer":
                    return {"status": False, "msg": "Нельзя убить своего!"}
                if lobby["kills"].get(user) == lobby["round"]:
                    return {"status": False, "msg": "Одно убийство за раунд!"}

                rooms[rid].remove(target)
                lobby["dead"].add(target)
                lobby["bodies"].append({"name": target, "room": rid})
                lobby["kills"][user] = lobby["round"]
                print(f"[KILL] {user} убил {target} в комнате {rid}")

                entered = False
                if user in rooms[rid]:
                    entered = True
                elif len(rooms[rid]) < QUEST_ROOMS[rid]:
                    for pl in rooms.values():
                        if user in pl:
                            pl.remove(user)
                    rooms[rid].append(user)
                    entered = True
                return {"status": True, "entered": entered,
                        "lobby": self.lobby_state(code, lobby, user)}

        if action == "report":
            with self.lobby_lock:
                code, lobby = self.find_lobby(user)
                if not lobby or not lobby.get("started"):
                    return {"status": False, "msg": "Игра не идёт"}
                if lobby.get("winner") or lobby.get("meeting"):
                    return {"status": False, "msg": "Сейчас нельзя!"}
                if user in lobby["dead"]:
                    return {"status": False, "msg": "Вы выбыли из игры!"}
                rooms = lobby.setdefault("rooms", {})
                bodies = lobby["bodies"]
                rid = next((r for r, pl in rooms.items()
                            if user in pl and any(b["room"] == r for b in bodies)), None)
                if rid is None:
                    return {"status": False, "msg": "Здесь нет тела!"}
                self.start_meeting(lobby, user, rid)
                print(f"[MEETING] {user} сообщил о теле в комнате {rid}")
                return {"status": True, "lobby": self.lobby_state(code, lobby, user)}

        if action in ("vote", "chat"):
            with self.lobby_lock:
                code, lobby = self.find_lobby(user)
                if not lobby:
                    return {"status": False, "closed": True, "msg": "Вы не в лобби"}
                self.tick(lobby)
                m = lobby.get("meeting")
                if not m or m["phase"] != "vote":
                    return {"status": False, "msg": "Голосование не идёт"}
                if user in lobby["dead"]:
                    return {"status": False, "msg": "Вы выбыли из игры!"}
                if action == "vote":
                    if user in m["votes"]:
                        return {"status": False, "msg": "Вы уже проголосовали!"}
                    target = str(msg.get("target", ""))
                    names = lobby["players"] + lobby.get("bots", [])
                    if target != "SKIP" and (target == user or target not in names
                                             or target in lobby["dead"]):
                        return {"status": False, "msg": "Нельзя голосовать за этого игрока"}
                    m["votes"][user] = target
                else:
                    text = str(msg.get("text", "")).strip()[:CHAT_MAX_LEN]
                    if not text:
                        return {"status": False, "msg": "Пустое сообщение"}
                    m["chat"].append({"name": user, "text": text})
                    del m["chat"][:-100]
                return {"status": True, "lobby": self.lobby_state(code, lobby, user)}

        if action == "check_player":
            with self.lobby_lock:
                code, lobby = self.find_lobby(user)
                if not lobby or not lobby.get("started"):
                    return {"status": False, "closed": not lobby, "msg": "Игра не идёт"}
                if lobby.get("winner") or lobby.get("meeting"):
                    return {"status": False, "msg": "Сейчас нельзя!"}
                roles = lobby["roles"]
                if roles.get(user) != "detective" or user in lobby["dead"]:
                    return {"status": False, "msg": "Вы не можете проверять!"}
                target = str(msg.get("target", ""))
                if target == user or target not in roles or target in lobby["known_dead"]:
                    return {"status": False, "msg": "Нельзя проверить этого игрока"}
                rnd = lobby["round"]
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