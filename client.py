import pygame
import sys
import os
import socket
import json
import random

pygame.init()
WIDTH, HEIGHT = 1000, 650
SCREEN = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Cyber-Mafia — Detroit Edition")
FONT = pygame.font.SysFont("Consolas", 18, bold=True)
SMALL_FONT = pygame.font.SysFont("Consolas", 16, bold=True)
TITLE_FONT = pygame.font.SysFont("Consolas", 32, bold=True)

COLOR_BG = (10, 16, 26)
COLOR_HUD = (0, 212, 255)
COLOR_TEXT = (220, 245, 255)
COLOR_DIM = (110, 140, 160)
COLOR_DARK_BOX = (15, 28, 44)
COLOR_DEV_RED = (255, 40, 80)
COLOR_ACTIVE = (0, 80, 120)
COLOR_GREEN = (60, 220, 120)
COLOR_YELLOW = (255, 200, 60)

STORY_TEXT = [
    "USA, 2038.",
    "Androids have existed for over 15 years, thanks to Elijah Kamski, who created them and every year they progress and become even better.",
    "However, over the past year, androids have begun to snap and become deviants.",
    "They ignore human orders, can harm people, and are even capable of murder.",
    "You are an android working in the mansion of the wealthy billionaire Elijah Kamski.",
    "Other androids work in his house besides you, but one of you is a deviant who will not hesitate to kill you to obtain critical information from the home of the androids' creator.",
    "You need to find the deviant. Good luck.",
]

# роль -> (название, цвет, описание)
ROLE_INFO = {
    "killer": ("DEVIANT", COLOR_DEV_RED,
               "You are the deviant. Steal critical data from Kamski's house while the androids are busy. In the rooms you have special tasks: hack the terminals. You can kill an android inside a room, even a full one: the victim's place is yours. One kill per round."),
    "detective": ("DETECTIVE", COLOR_YELLOW,
                  "You are the detective. Do your tasks like everyone else. Once per round you can check one player and find out if he is a deviant."),
    "peaceful": ("ANDROID", COLOR_HUD,
                 "You are a loyal android. Do your tasks in the rooms. If you find a body, report it. When all androids finish their tasks or all deviants are ejected, you win."),
}

ROOM_NAMES = {1: "Tower", 2: "Center", 3: "East wing", 4: "Terrace", 5: "South wing"}

# ---------------- КОСТЮМЫ ----------------
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
ASSET_FILES = {
    "body": "body.png",
    "hair": "hair.png",
    "clothes": "clothes.png",
    "led_blue": "led_blue.png",
    "led_yellow": "led_yellow.png",
    "led_red": "led_red.png",
}
COSTUME_ITEMS = [
    ("hair", "Hair"),
    ("clothes", "Clothes"),
    ("led_blue", "LED blue"),
    ("led_yellow", "LED yellow"),
    ("led_red", "LED red"),
]
PREVIEW_SCALE = 0.28
PREVIEW_CROP = pygame.Rect(110, 30, 360, 480)
PREVIEW_POS = (70, 100)


def load_assets():
    """Загружаем слои костюма из папки assets."""
    layers, thumbs, missing = {}, {}, []
    for key, fname in ASSET_FILES.items():
        path = os.path.join(ASSET_DIR, fname)
        try:
            img = pygame.image.load(path).convert_alpha()
        except Exception:
            missing.append(fname)
            continue
        w, h = img.get_size()
        layers[key] = pygame.transform.smoothscale(
            img, (max(1, int(w * PREVIEW_SCALE)), max(1, int(h * PREVIEW_SCALE))))

        box = img.get_bounding_rect()
        if box.w > 0 and box.h > 0:
            crop = img.subsurface(box).copy()
            k = min(90 / box.w, 70 / box.h)
            thumbs[key] = pygame.transform.smoothscale(
                crop, (max(1, int(box.w * k)), max(1, int(box.h * k))))
    return layers, thumbs, missing


ASSET_LAYERS, ASSET_THUMBS, ASSET_MISSING = load_assets()

# ---------------- КАРТА ----------------
MAP_S = 0.737
MAP_OX = 140
MAP_OY = 75

MAP_FLOOR = (26, 42, 62)
MAP_WALL = (95, 120, 145)

MAP_ROOMS = [
    (110, 80, 375, 375),     # башня слева
    (110, 375, 365, 440),    # полоса под башней (без задания)
    (375, 215, 670, 440),    # центр
    (670, 145, 915, 440),    # правая часть
    (370, 440, 930, 540),    # главный коридор
    (375, 540, 915, 720),    # нижняя часть
]
MAP_TERRACE = (375, 80, 670, 215)
MAP_ROUND = (985, 515, 85)

QUEST_RECTS = {
    1: (110, 80, 375, 375),
    2: (375, 215, 670, 440),
    3: (670, 145, 915, 440),
    4: MAP_TERRACE,
    5: (375, 540, 915, 720),
}

MAP_DOORS = [
    (715, 433, 40, 14), (820, 433, 40, 14), (600, 433, 40, 14), (420, 433, 40, 14),
    (230, 368, 30, 14),
    (362, 400, 16, 30),
    (470, 533, 40, 14), (620, 533, 40, 14), (790, 533, 40, 14),
    (580, 208, 40, 14),
    (663, 230, 14, 40),
    (905, 470, 20, 50),
]


def mp(x, y):
    return int(MAP_OX + (x - 100) * MAP_S), int(MAP_OY + (y - 30) * MAP_S)


def mrect(x1, y1, x2, y2):
    ax, ay = mp(x1, y1)
    bx, by = mp(x2, y2)
    return pygame.Rect(ax, ay, bx - ax, by - ay)


def wrap_lines(text, font, max_w):
    """Разбить текст на строки по ширине."""
    lines, cur = [], ""
    for w in text.split():
        test = (cur + " " + w).strip()
        if font.size(test)[0] > max_w and cur:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def draw_shadow(x, y, filled, edge):
    """Силуэт человека: закрашенный (занято) или только контур (свободно)."""
    if filled:
        pygame.draw.circle(SCREEN, (4, 7, 12), (x + 11, y + 6), 6)
        pygame.draw.ellipse(SCREEN, (4, 7, 12), (x + 2, y + 14, 18, 22))
        pygame.draw.circle(SCREEN, edge, (x + 11, y + 6), 6, 1)
        pygame.draw.ellipse(SCREEN, edge, (x + 2, y + 14, 18, 22), 1)
    else:
        dim = (70, 92, 115)
        pygame.draw.circle(SCREEN, dim, (x + 11, y + 6), 6, 1)
        pygame.draw.ellipse(SCREEN, dim, (x + 2, y + 14, 18, 22), 1)


def draw_map():
    wt = max(3, int(8 * MAP_S))

    t = mrect(*MAP_TERRACE)
    pygame.draw.rect(SCREEN, (18, 30, 46), t)
    pygame.draw.rect(SCREEN, COLOR_DIM, t, 1)
    for px in (475, 578):
        cx, cy = mp(px, 85)
        pygame.draw.rect(SCREEN, MAP_WALL, (cx - 4, cy - 4, 8, 8))

    for r in MAP_ROOMS:
        pygame.draw.rect(SCREEN, MAP_FLOOR, mrect(*r))
    rx, ry, rr = MAP_ROUND
    cx, cy = mp(rx, ry)
    pygame.draw.circle(SCREEN, MAP_FLOOR, (cx, cy), int(rr * MAP_S))

    for r in MAP_ROOMS:
        pygame.draw.rect(SCREEN, MAP_WALL, mrect(*r), wt)
    pygame.draw.circle(SCREEN, MAP_WALL, (cx, cy), int(rr * MAP_S), wt)

    for d in MAP_DOORS:
        x, y, w, h = d
        pygame.draw.rect(SCREEN, MAP_FLOOR, mrect(x, y, x + w, y + h))

    lbl = FONT.render("ВХОД", True, COLOR_HUD)
    SCREEN.blit(lbl, (cx - lbl.get_width() // 2, cy - lbl.get_height() // 2))


class CyberClient:
    def __init__(self):
        self.sock = None
        self.connected = False
        self.rbuf = b""

        self.current_screen = "MAIN"
        self.user = ""
        self.skin = "RK800"
        self.outfit = {"hair": True, "clothes": True, "led": None}
        self.exit_confirm = False

        self.input_user = ""
        self.input_pass = ""
        self.input_code = ""
        self.active_field = None
        self.login_msg = ""
        self.join_msg = ""
        self.lobby_msg = ""
        self.notice = ""

        self.lobby = None
        self.last_poll = 0
        self.click_pos = None

        # задания в комнатах
        self.quest_room = None
        self.quest_done = False
        self.dirt = []            # задание со шваброй (мирные)
        self.nodes = []           # задание убийц: узлы
        self.next_node = 1
        self.room_msg = ""
        self.room_msg_until = 0

        # роли, убийства, голосование
        self.role_seen = False
        self.dead_seen = False
        self.check_open = False
        self.kill_room = None
        self.chat_input = ""

        self.try_connect()

    # ---------- сеть ----------
    def try_connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(2)
            self.sock.connect(('127.0.0.1', 5555))
            self.connected = True
            self.rbuf = b""
        except Exception:
            self.connected = False
            print("Ошибка: Сервер не запущен!")
        return self.connected

    def drop_connection(self):
        try:
            self.sock.close()
        except Exception:
            pass
        self.connected = False
        self.user = ""
        self.lobby = None

    def send_request(self, payload):
        if not self.connected and not self.try_connect():
            return None
        try:
            self.sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            while b"\n" not in self.rbuf:
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise ConnectionError
                self.rbuf += chunk
            line, self.rbuf = self.rbuf.split(b"\n", 1)
            return json.loads(line.decode("utf-8"))
        except Exception:
            self.drop_connection()
            return None

    # ---------- навигация ----------
    def go(self, screen):
        self.current_screen = screen
        self.quest_room = None
        self.kill_room = None
        self.check_open = False
        if screen != "GAME":
            self.role_seen = False
            self.dead_seen = False
            self.chat_input = ""
        self.notice = ""
        self.login_msg = ""
        self.join_msg = ""
        self.lobby_msg = ""

    def connection_lost(self):
        self.go("MAIN")
        self.notice = "Связь с сервером потеряна!"

    # ---------- костюм ----------
    def set_outfit_from_skin(self, skin):
        """Разбираем строку скина вида 'hair,clothes,led_blue'."""
        if not skin or skin == "RK800":
            self.outfit = {"hair": True, "clothes": True, "led": None}
            return
        parts = skin.split(",")
        self.outfit = {
            "hair": "hair" in parts,
            "clothes": "clothes" in parts,
            "led": next((p for p in parts if p.startswith("led_")), None),
        }

    def skin_string(self):
        parts = [k for k in ("hair", "clothes") if self.outfit[k]]
        if self.outfit["led"]:
            parts.append(self.outfit["led"])
        return ",".join(parts) or "none"

    def costume_on(self, key):
        if key in ("hair", "clothes"):
            return self.outfit[key]
        return self.outfit["led"] == key

    def toggle_costume(self, key):
        if key in ("hair", "clothes"):
            self.outfit[key] = not self.outfit[key]
        else:
            self.outfit["led"] = None if self.outfit["led"] == key else key
        self.skin = self.skin_string()
        if self.user:
            self.send_request({"action": "update_skin", "skin": self.skin})

    # ---------- логика ----------
    def ensure_user(self):
        if self.user:
            return True
        res = self.send_request({"action": "guest"})
        if res and res.get("status"):
            self.user = res["username"]
            return True
        self.notice = "Сервер недоступен!"
        return False

    def do_login(self):
        if not self.input_user.strip():
            self.login_msg = "Введите имя!"
            return
        res = self.send_request({"action": "login",
                                 "username": self.input_user,
                                 "password": self.input_pass})
        if res is None:
            self.login_msg = "Сервер недоступен!"
        elif res.get("status"):
            self.user = res.get("username", self.input_user)
            self.skin = res.get("skin") or "RK800"
            self.set_outfit_from_skin(self.skin)
            self.go("MAIN")
        else:
            self.login_msg = res.get("msg", "Ошибка входа")

    def enter_lobby(self, lobby):
        self.lobby = lobby
        self.last_poll = pygame.time.get_ticks()
        self.go("GAME" if lobby.get("started") else "LOBBY")

    def do_create_lobby(self):
        if not self.ensure_user():
            return
        res = self.send_request({"action": "create_lobby"})
        if res is None:
            self.connection_lost()
        elif res.get("status"):
            self.enter_lobby(res["lobby"])
        else:
            self.notice = res.get("msg", "Ошибка")

    def do_join(self):
        code = self.input_code.strip()
        if len(code) != 4:
            self.join_msg = "Код — 4 цифры!"
            return
        if not self.ensure_user():
            self.join_msg = self.notice
            return
        res = self.send_request({"action": "join_lobby", "code": code})
        if res is None:
            self.connection_lost()
        elif res.get("status"):
            self.enter_lobby(res["lobby"])
        else:
            self.join_msg = res.get("msg", "Ошибка")

    def leave_lobby(self):
        self.send_request({"action": "leave_lobby"})
        self.lobby = None
        self.go("MAIN")

    def start_game(self):
        self.apply_lobby_response(self.send_request({"action": "start_game"}))

    def apply_lobby_response(self, res):
        if res is None:
            self.connection_lost()
        elif res.get("status"):
            self.lobby = res["lobby"]
            self.lobby_msg = ""
            if self.lobby.get("started") and self.current_screen == "LOBBY":
                self.go("GAME")
        elif res.get("closed"):
            self.lobby = None
            self.go("MAIN")
            self.notice = res.get("msg", "Лобби закрыто")
        else:
            self.lobby_msg = res.get("msg", "Ошибка")

    def poll_lobby(self):
        now = pygame.time.get_ticks()
        interval = 500 if (self.lobby and self.lobby.get("meeting")) else 1000
        if now - self.last_poll > interval:
            self.last_poll = now
            self.apply_lobby_response(self.send_request({"action": "get_lobby"}))

    def change_setting(self, key, value):
        if not self.lobby or self.lobby["host"] != self.user:
            return
        settings = {k: self.lobby[k] for k in ("size", "killers", "detectives", "quests")}
        settings[key] = value
        res = self.send_request({"action": "update_settings", **settings})
        self.apply_lobby_response(res)

    def show_msg(self, text):
        self.room_msg = text
        self.room_msg_until = pygame.time.get_ticks() + 2500

    def room_players(self, rid):
        for r in self.lobby["rooms"]:
            if r["id"] == rid:
                return r["players"]
        return []

    # ---------- задания в комнатах ----------
    def try_enter_room(self, rid):
        res = self.send_request({"action": "enter_room", "room": rid})
        if res is None:
            self.connection_lost()
        elif res.get("status"):
            self.lobby = res["lobby"]
            self.open_quest(rid)
        elif res.get("closed"):
            self.apply_lobby_response(res)
        else:
            self.show_msg(res.get("msg", "Ошибка"))

    def open_quest(self, rid):
        self.quest_room = rid
        self.quest_done = False
        if self.lobby.get("my_role") == "killer":
            cells = [(x, y) for x in range(310, 720, 90) for y in (250, 350)]
            self.nodes = random.sample(cells, 5)
            self.next_node = 1
        else:
            self.dirt = [{"x": random.randint(300, 700),
                          "y": random.randint(230, 390),
                          "left": 40} for _ in range(6)]

    def close_quest(self):
        res = self.send_request({"action": "exit_room"})
        self.quest_room = None
        if res is None:
            self.connection_lost()
        elif res.get("status"):
            self.lobby = res["lobby"]

    def finish_quest(self):
        """Сообщаем серверу, что задание выполнено."""
        self.quest_done = True
        res = self.send_request({"action": "complete_quest", "room": self.quest_room})
        if res is None:
            self.connection_lost()
        elif res.get("status"):
            self.lobby = res["lobby"]
        else:
            self.show_msg(res.get("msg", "Ошибка"))

    # ---------- убийство, репорт, голосование ----------
    def do_kill(self, rid, target):
        res = self.send_request({"action": "kill", "room": rid, "target": target})
        if res is None:
            self.connection_lost()
            return
        if res.get("status"):
            self.lobby = res["lobby"]
            self.kill_room = None
            if res.get("entered") and self.quest_room != rid:
                self.open_quest(rid)
        else:
            self.kill_room = None
            self.show_msg(res.get("msg", "Ошибка"))

    def do_report(self):
        res = self.send_request({"action": "report"})
        if res is None:
            self.connection_lost()
        elif res.get("status"):
            self.lobby = res["lobby"]
            self.quest_room = None
            self.kill_room = None
        else:
            self.show_msg(res.get("msg", "Ошибка"))

    def do_vote(self, target):
        res = self.send_request({"action": "vote", "target": target})
        if res is None:
            self.connection_lost()
        elif res.get("status"):
            self.lobby = res["lobby"]
        else:
            self.show_msg(res.get("msg", "Ошибка"))

    def send_chat(self):
        text = self.chat_input.strip()
        if not text:
            return
        self.chat_input = ""
        res = self.send_request({"action": "chat", "text": text})
        if res is None:
            self.connection_lost()
        elif res.get("status"):
            self.lobby = res["lobby"]
        else:
            self.show_msg(res.get("msg", "Ошибка"))

    def draw_quest(self):
        lob = self.lobby
        rid = self.quest_room
        is_killer = lob.get("my_role") == "killer"
        alive = lob.get("alive", True)
        mine = lob.get("my_done", [])
        can_task = self.quest_done or (alive and rid not in mine and len(mine) < lob["quests"])
        body_here = rid in lob.get("body_rooms", [])

        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        SCREEN.blit(overlay, (0, 0))
        pygame.draw.rect(SCREEN, (12, 22, 36), (250, 100, 500, 440))
        pygame.draw.rect(SCREEN, COLOR_DEV_RED if is_killer else COLOR_HUD,
                         (250, 100, 500, 440), 2)

        if body_here:
            SCREEN.blit(FONT.render("A BODY IS HERE!", True, COLOR_DEV_RED), (270, 106))
        else:
            SCREEN.blit(SMALL_FONT.render(ROOM_NAMES.get(rid, "Room"), True, COLOR_DIM),
                        (270, 108))

        if not can_task:
            SCREEN.blit(FONT.render("Nothing to do here", True, COLOR_HUD), (270, 140))
            SCREEN.blit(FONT.render("You can still look around and report a body",
                                    True, COLOR_DIM), (270, 163))
        elif is_killer:
            SCREEN.blit(FONT.render("SPECIAL TASK: Steal data from the terminal",
                                    True, COLOR_DEV_RED), (270, 140))
            SCREEN.blit(FONT.render("Click the nodes in order 1 to 5",
                                    True, COLOR_DIM), (270, 163))
        else:
            SCREEN.blit(FONT.render("QUEST: Clean the floor with the mop",
                                    True, COLOR_HUD), (270, 140))
            SCREEN.blit(FONT.render("Hold the mouse button and scrub the dirt",
                                    True, COLOR_DIM), (270, 163))

        floor = pygame.Rect(270, 190, 460, 230)
        pygame.draw.rect(SCREEN, (30, 50, 72), floor)
        pygame.draw.rect(SCREEN, COLOR_HUD, floor, 1)

        mx, my = pygame.mouse.get_pos()
        done = False
        msg = ""

        if not can_task:
            if not alive:
                why = "You are out of the game."
            elif rid in mine:
                why = "You already finished the task here."
            else:
                why = "You finished all your tasks."
            t = FONT.render(why, True, COLOR_DIM)
            SCREEN.blit(t, (floor.centerx - t.get_width() // 2, floor.centery - 9))
        elif is_killer:
            for i, (nx, ny) in enumerate(self.nodes):
                number = i + 1
                rect = pygame.Rect(nx - 28, ny - 28, 56, 56)
                got = number < self.next_node
                pygame.draw.rect(SCREEN, (20, 90, 60) if got else COLOR_DARK_BOX, rect)
                pygame.draw.rect(SCREEN, COLOR_GREEN if got else COLOR_DEV_RED, rect, 2)
                t = FONT.render(str(number), True, COLOR_TEXT)
                SCREEN.blit(t, (rect.centerx - t.get_width() // 2,
                                rect.centery - t.get_height() // 2))
                if (self.next_node <= 5 and self.click_pos and not self.exit_confirm
                        and rect.collidepoint(self.click_pos)):
                    self.click_pos = None
                    if number == self.next_node:
                        self.next_node += 1
                    else:
                        self.next_node = 1   # ошибка: начинаем заново
            done = self.next_node > 5
            msg = "Data stolen! +1 stolen" if done else f"Next node: {self.next_node}"
        else:
            pressed = pygame.mouse.get_pressed()[0] and not self.exit_confirm
            for d in self.dirt:
                if d["left"] > 0:
                    if pressed and ((mx - d["x"]) ** 2 + (my - d["y"]) ** 2) ** 0.5 < 32:
                        d["left"] -= 1
                    pygame.draw.circle(SCREEN, (90, 70, 40), (d["x"], d["y"]),
                                       8 + d["left"] // 2)
            done = all(d["left"] <= 0 for d in self.dirt)
            if done:
                msg = "Done! Floor is clean. +1 task"
            else:
                msg = "Dirty spots left: " + str(sum(1 for d in self.dirt if d["left"] > 0))
            if floor.collidepoint(mx, my):  # швабра
                pygame.draw.line(SCREEN, COLOR_TEXT, (mx, my), (mx + 25, my - 45), 4)
                pygame.draw.rect(SCREEN, COLOR_HUD, (mx - 14, my - 4, 28, 8))

        if msg:
            SCREEN.blit(FONT.render(msg, True, COLOR_GREEN if done else COLOR_TEXT),
                        (270, 430))

        if done and not self.quest_done:
            self.finish_quest()
            if self.quest_room is None:  # связь потеряна
                return

        # убийца: убить того, кто в этой же комнате
        if is_killer and alive:
            others = [p for p in self.room_players(rid)
                      if p != self.user and p not in lob.get("teammates", [])]
            if others:
                if lob.get("can_kill"):
                    if self.draw_button(f"Kill {others[0]}", 270, 458, 230, 34):
                        self.do_kill(rid, others[0])
                else:
                    SCREEN.blit(SMALL_FONT.render("Kill already used this round",
                                                  True, COLOR_DIM), (270, 467))

        if self.draw_button("Close", 400, 496, 200, 34):
            self.close_quest()
            return
        if body_here and alive:
            if self.draw_button("Report", 620, 496, 110, 34):
                self.do_report()

    def draw_kill_panel(self):
        lob = self.lobby
        rid = self.kill_room
        players = self.room_players(rid)
        victims = [p for p in players if p != self.user
                   and p not in lob.get("teammates", [])]
        if len(players) < 2 and not victims:
            self.kill_room = None
            return

        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        SCREEN.blit(overlay, (0, 0))
        pygame.draw.rect(SCREEN, (12, 22, 36), (300, 170, 400, 290))
        pygame.draw.rect(SCREEN, COLOR_DEV_RED, (300, 170, 400, 290), 2)

        t = FONT.render(f"{ROOM_NAMES.get(rid, 'Room')} is full", True, COLOR_DEV_RED)
        SCREEN.blit(t, (500 - t.get_width() // 2, 185))
        t = SMALL_FONT.render("Kill someone inside to take the place", True, COLOR_DIM)
        SCREEN.blit(t, (500 - t.get_width() // 2, 212))

        y = 250
        if not victims:
            SCREEN.blit(SMALL_FONT.render("No targets here", True, COLOR_DIM), (400, y + 8))
        for name in victims:
            if lob.get("can_kill"):
                if self.draw_button(f"Kill {name}", 350, y, 300, 40):
                    self.do_kill(rid, name)
                    return
            else:
                pygame.draw.rect(SCREEN, COLOR_DARK_BOX, (350, y, 300, 40))
                pygame.draw.rect(SCREEN, COLOR_DIM, (350, y, 300, 40), 1)
                t = SMALL_FONT.render("Kill already used this round", True, COLOR_DIM)
                SCREEN.blit(t, (500 - t.get_width() // 2, y + 11))
            y += 50

        if self.draw_button("Cancel", 400, 400, 200, 40):
            self.kill_room = None

    # ---------- голосование ----------
    def draw_meeting(self):
        lob = self.lobby
        m = lob["meeting"]
        alive = lob.get("alive", True)

        pygame.draw.rect(SCREEN, COLOR_BG, (0, 0, WIDTH, HEIGHT))
        t = TITLE_FONT.render("EMERGENCY MEETING", True, COLOR_DEV_RED)
        SCREEN.blit(t, (WIDTH // 2 - t.get_width() // 2, 14))
        t = SMALL_FONT.render(f"A body was reported by {m['reporter']}", True, COLOR_TEXT)
        SCREEN.blit(t, (WIDTH // 2 - t.get_width() // 2, 56))

        if m["phase"] == "result":
            self.draw_meeting_result(m)
            return

        SCREEN.blit(FONT.render(f"Time left: {m['left']}s", True, COLOR_YELLOW), (790, 26))

        # ---- левая панель: голосование ----
        pygame.draw.rect(SCREEN, (12, 22, 36), (40, 90, 440, 520))
        pygame.draw.rect(SCREEN, COLOR_HUD, (40, 90, 440, 520), 2)
        SCREEN.blit(FONT.render("Who is the deviant?", True, COLOR_HUD), (60, 100))

        cands = m["candidates"]
        can_vote = m.get("can_vote", False)
        my_vote = m.get("my_vote")
        voted = m.get("voted", [])

        if my_vote:
            info = "You voted: " + ("SKIP" if my_vote == "SKIP" else my_vote)
        elif can_vote:
            info = "Choose a player to eject"
        elif not alive:
            info = "You are out: you can only watch"
        else:
            info = "You cannot vote"
        SCREEN.blit(SMALL_FONT.render(info, True, COLOR_DIM), (60, 126))

        for i, name in enumerate(cands):
            x = 60 + (i % 2) * 210
            y = 155 + (i // 2) * 48
            if can_vote:
                if self.draw_button(name, x, y, 200, 40, selected=(my_vote == name)):
                    self.do_vote(name)
            else:
                pygame.draw.rect(SCREEN, COLOR_ACTIVE if my_vote == name else COLOR_DARK_BOX,
                                 (x, y, 200, 40))
                pygame.draw.rect(SCREEN, COLOR_DIM, (x, y, 200, 40), 1)
                t = FONT.render(name, True, COLOR_DIM)
                SCREEN.blit(t, (x + (200 - t.get_width()) // 2, y + 10))
            if name in voted:
                pygame.draw.circle(SCREEN, COLOR_GREEN, (x + 186, y + 20), 5)

        sy = 155 + ((len(cands) + 1) // 2) * 48 + 6
        if can_vote:
            if self.draw_button("Skip vote", 60, sy, 200, 40, selected=(my_vote == "SKIP")):
                self.do_vote("SKIP")
        else:
            pygame.draw.rect(SCREEN, COLOR_ACTIVE if my_vote == "SKIP" else COLOR_DARK_BOX,
                             (60, sy, 200, 40))
            pygame.draw.rect(SCREEN, COLOR_DIM, (60, sy, 200, 40), 1)
            t = FONT.render("Skip vote", True, COLOR_DIM)
            SCREEN.blit(t, (60 + (200 - t.get_width()) // 2, sy + 10))
        SCREEN.blit(SMALL_FONT.render(f"Votes cast: {len(voted)}", True, COLOR_DIM),
                    (60, sy + 55))
        self.draw_room_msg(60, sy + 80)

        # ---- правая панель: чат ----
        pygame.draw.rect(SCREEN, (12, 22, 36), (500, 90, 460, 520))
        pygame.draw.rect(SCREEN, COLOR_HUD, (500, 90, 460, 520), 2)
        SCREEN.blit(FONT.render("Chat", True, COLOR_HUD), (510, 98))

        lines = []
        for c in m["chat"]:
            if c["name"] == "SYSTEM":
                col, text = COLOR_YELLOW, c["text"]
            else:
                col = COLOR_HUD if c["name"] == self.user else COLOR_TEXT
                text = f"{c['name']}: {c['text']}"
            for part in wrap_lines(text, SMALL_FONT, 435):
                lines.append((col, part))
        for i, (col, part) in enumerate(lines[-18:]):
            SCREEN.blit(SMALL_FONT.render(part, True, col), (510, 128 + i * 20))

        box = pygame.Rect(510, 535, 340, 38)
        can_chat = alive
        pygame.draw.rect(SCREEN, COLOR_ACTIVE if can_chat else COLOR_DARK_BOX, box)
        pygame.draw.rect(SCREEN, COLOR_HUD if can_chat else COLOR_DIM, box, 1)
        if can_chat:
            txt = self.chat_input
            while SMALL_FONT.size(txt + "_")[0] > 320:
                txt = txt[1:]
            cursor = "_" if (pygame.time.get_ticks() // 500) % 2 == 0 else ""
            SCREEN.blit(SMALL_FONT.render(txt + cursor, True, COLOR_TEXT), (518, 546))
            if self.draw_button("Send", 860, 535, 90, 38):
                self.send_chat()
            SCREEN.blit(SMALL_FONT.render("Type a message and press Enter",
                                          True, COLOR_DIM), (510, 582))
        else:
            SCREEN.blit(SMALL_FONT.render("Dead players cannot chat", True, COLOR_DIM),
                        (518, 546))

    def draw_meeting_result(self, m):
        res = m["result"]
        pygame.draw.rect(SCREEN, (12, 22, 36), (200, 100, 600, 420))
        pygame.draw.rect(SCREEN, COLOR_YELLOW, (200, 100, 600, 420), 2)
        t = TITLE_FONT.render("VOTING RESULT", True, COLOR_YELLOW)
        SCREEN.blit(t, (500 - t.get_width() // 2, 120))

        if res["ejected"]:
            t = FONT.render(f"{res['ejected']} was ejected.", True, COLOR_TEXT)
            SCREEN.blit(t, (500 - t.get_width() // 2, 190))
            if res["deviant"]:
                t = FONT.render(f"{res['ejected']} WAS A DEVIANT!", True, COLOR_DEV_RED)
            else:
                t = FONT.render(f"{res['ejected']} was NOT a deviant.", True, COLOR_GREEN)
            SCREEN.blit(t, (500 - t.get_width() // 2, 220))
        else:
            t = FONT.render("No one was ejected.", True, COLOR_TEXT)
            SCREEN.blit(t, (500 - t.get_width() // 2, 200))

        SCREEN.blit(SMALL_FONT.render("Votes:", True, COLOR_DIM), (230, 275))
        tally = sorted(res["tally"].items(), key=lambda kv: -kv[1])[:8]
        if not tally:
            SCREEN.blit(SMALL_FONT.render("nobody voted", True, COLOR_DIM), (230, 300))
        for i, (name, n) in enumerate(tally):
            label = "Skip" if name == "SKIP" else name
            SCREEN.blit(SMALL_FONT.render(f"{label}: {n}", True, COLOR_TEXT),
                        (230, 300 + i * 22))

        t = SMALL_FONT.render(f"Back to the game in {m['left']}s", True, COLOR_DIM)
        SCREEN.blit(t, (500 - t.get_width() // 2, 490))

    # ---------- детектив ----------
    def do_check(self, target):
        res = self.send_request({"action": "check_player", "target": target})
        if res is None:
            self.connection_lost()
        elif res.get("status"):
            self.lobby = res["lobby"]
        else:
            self.show_msg(res.get("msg", "Ошибка"))

    def draw_check_panel(self):
        lob = self.lobby
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        SCREEN.blit(overlay, (0, 0))
        pygame.draw.rect(SCREEN, (12, 22, 36), (250, 100, 500, 450))
        pygame.draw.rect(SCREEN, COLOR_YELLOW, (250, 100, 500, 450), 2)

        SCREEN.blit(FONT.render("DETECTIVE: check a player", True, COLOR_YELLOW), (270, 118))
        can = lob.get("can_check", False)
        status = "Check ready" if can else "Check already used this round"
        SCREEN.blit(SMALL_FONT.render(
            f"Round {lob.get('round', 1)} ({lob.get('round_left', 0)}s left). {status}",
            True, COLOR_GREEN if can else COLOR_DIM), (270, 145))

        names = [s["name"] for s in lob["slots"]
                 if s["name"] != self.user and not s.get("dead")]
        for i, name in enumerate(names):
            x = 270 + (i % 2) * 240
            y = 180 + (i // 2) * 46
            if can:
                if self.draw_button(name, x, y, 220, 38):
                    self.do_check(name)
                    break
            else:
                pygame.draw.rect(SCREEN, COLOR_DARK_BOX, (x, y, 220, 38))
                pygame.draw.rect(SCREEN, COLOR_DIM, (x, y, 220, 38), 1)
                t = FONT.render(name, True, COLOR_DIM)
                SCREEN.blit(t, (x + (220 - t.get_width()) // 2, y + 9))

        SCREEN.blit(SMALL_FONT.render("Your checks:", True, COLOR_TEXT), (270, 375))
        for i, c in enumerate(lob.get("checks", [])[-3:]):
            if c["deviant"]:
                txt, col = f"Round {c['round']}: {c['target']} is a DEVIANT!", COLOR_DEV_RED
            else:
                txt, col = f"Round {c['round']}: {c['target']} is not a deviant", COLOR_GREEN
            SCREEN.blit(SMALL_FONT.render(txt, True, col), (270, 398 + i * 22))

        self.draw_room_msg(270, 468)

        if self.draw_button("Close", 400, 495, 200, 40):
            self.check_open = False

    # ---------- рисование ----------
    def draw_button(self, text, x, y, w, h, modal=False, selected=False):
        active = modal or not self.exit_confirm

        mouse = pygame.mouse.get_pos()
        is_hover = active and x <= mouse[0] <= x + w and y <= mouse[1] <= y + h

        border_color = COLOR_DEV_RED if is_hover else COLOR_HUD
        if selected:
            bg_color = COLOR_ACTIVE
        else:
            bg_color = (20, 35, 55) if is_hover else (10, 18, 28)

        pygame.draw.rect(SCREEN, bg_color, (x, y, w, h))
        pygame.draw.rect(SCREEN, border_color, (x, y, w, h), 2)

        txt = FONT.render(text, True, COLOR_TEXT)
        SCREEN.blit(txt, (x + (w - txt.get_width()) // 2, y + (h - txt.get_height()) // 2))

        if active and self.click_pos:
            cx, cy = self.click_pos
            if x <= cx <= x + w and y <= cy <= y + h:
                self.click_pos = None
                return True
        return False

    def draw_room_msg(self, x, y):
        if self.room_msg and pygame.time.get_ticks() < self.room_msg_until:
            SCREEN.blit(FONT.render(self.room_msg, True, COLOR_DEV_RED), (x, y))

    def draw_customize(self):
        pygame.draw.rect(SCREEN, (12, 22, 36), (60, 90, 380, 500))
        pygame.draw.rect(SCREEN, COLOR_HUD, (60, 90, 380, 500), 2)

        if "body" not in ASSET_LAYERS:
            t = SMALL_FONT.render("body.png not found", True, COLOR_DEV_RED)
            SCREEN.blit(t, (250 - t.get_width() // 2, 330))
        else:
            order = ["body"]
            if self.outfit["clothes"]:
                order.append("clothes")
            if self.outfit["hair"]:
                order.append("hair")
            if self.outfit["led"]:
                order.append(self.outfit["led"])
            for key in order:
                layer = ASSET_LAYERS.get(key)
                if layer:
                    SCREEN.blit(layer, PREVIEW_POS, PREVIEW_CROP)

        SCREEN.blit(FONT.render("Costumes", True, COLOR_HUD), (500, 95))
        SCREEN.blit(SMALL_FONT.render("Click an item to put it on / take it off",
                                      True, COLOR_DIM), (500, 118))

        mouse = pygame.mouse.get_pos()
        for i, (key, label) in enumerate(COSTUME_ITEMS):
            x = 500 + (i % 3) * 150
            y = 150 + (i // 3) * 160
            rect = pygame.Rect(x, y, 130, 140)
            on = self.costume_on(key)
            hover = rect.collidepoint(mouse) and not self.exit_confirm

            pygame.draw.rect(SCREEN, COLOR_ACTIVE if on else COLOR_DARK_BOX, rect)
            pygame.draw.rect(SCREEN, (38, 58, 82), (x + 10, y + 10, 110, 90))
            thumb = ASSET_THUMBS.get(key)
            if thumb:
                SCREEN.blit(thumb, (x + 65 - thumb.get_width() // 2,
                                    y + 55 - thumb.get_height() // 2))
            border = COLOR_GREEN if on else (COLOR_DEV_RED if hover else COLOR_HUD)
            pygame.draw.rect(SCREEN, border, rect, 3 if (on or hover) else 2)

            t = SMALL_FONT.render(label, True, COLOR_TEXT)
            SCREEN.blit(t, (rect.centerx - t.get_width() // 2, y + 110))

            if (self.click_pos and not self.exit_confirm
                    and rect.collidepoint(self.click_pos)):
                self.click_pos = None
                self.toggle_costume(key)

        if ASSET_MISSING:
            SCREEN.blit(SMALL_FONT.render("Missing files in the assets folder:",
                                          True, COLOR_DEV_RED), (500, 475))
            yy = 497
            for line in wrap_lines(", ".join(ASSET_MISSING), SMALL_FONT, 450):
                SCREEN.blit(SMALL_FONT.render(line, True, COLOR_DEV_RED), (500, yy))
                yy += 20
        elif not self.user:
            SCREEN.blit(SMALL_FONT.render("Log in to save your costume.",
                                          True, COLOR_DIM), (500, 475))

        if self.draw_button("Back", 400, 598, 200, 45):
            self.go("MAIN")

    def draw_story(self):
        y = 90
        for line in STORY_TEXT:
            for part in wrap_lines(line, SMALL_FONT, WIDTH - 140):
                SCREEN.blit(SMALL_FONT.render(part, True, COLOR_TEXT), (70, y))
                y += 24
            y += 14

        if self.draw_button("Back", 400, 580, 200, 45):
            self.go("MAIN")

    def draw_progress(self):
        """Шкала выполнения задач (сверху по центру)."""
        prog = self.lobby.get("progress", {"done": 0, "total": 0})
        done, total = prog["done"], prog["total"]
        x, y, w, h = 300, 62, 400, 18
        pygame.draw.rect(SCREEN, COLOR_DARK_BOX, (x, y, w, h))
        if total > 0:
            fill = int(w * min(done / total, 1))
            pygame.draw.rect(SCREEN, COLOR_GREEN if done >= total else COLOR_HUD,
                             (x, y, fill, h))
            for i in range(1, total):
                dx = x + int(w * i / total)
                pygame.draw.line(SCREEN, COLOR_BG, (dx, y), (dx, y + h), 1)
        pygame.draw.rect(SCREEN, COLOR_HUD, (x, y, w, h), 2)

        label = f"TASKS {done}/{total}"
        if total > 0 and done >= total:
            label = "ALL TASKS DONE!"
        t = SMALL_FONT.render(label, True, COLOR_TEXT)
        SCREEN.blit(t, (x + (w - t.get_width()) // 2, y + h + 4))

        mine = len(self.lobby.get("my_done", []))
        word = "Stolen data" if self.lobby.get("my_role") == "killer" else "My tasks"
        m = SMALL_FONT.render(f"{word}: {mine}/{self.lobby['quests']}", True, COLOR_DIM)
        SCREEN.blit(m, (720, y + 1))
        if "round" in self.lobby:
            r = SMALL_FONT.render(
                f"Round {self.lobby['round']} ({self.lobby['round_left']}s)", True, COLOR_DIM)
            SCREEN.blit(r, (720, y + 22))

    def draw_role_modal(self):
        role = self.lobby["my_role"]
        name, color, desc = ROLE_INFO[role]
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        SCREEN.blit(overlay, (0, 0))
        pygame.draw.rect(SCREEN, (12, 22, 36), (230, 150, 540, 340))
        pygame.draw.rect(SCREEN, color, (230, 150, 540, 340), 2)

        t = SMALL_FONT.render("YOUR ROLE", True, COLOR_DIM)
        SCREEN.blit(t, (500 - t.get_width() // 2, 170))
        t = TITLE_FONT.render(name, True, color)
        SCREEN.blit(t, (500 - t.get_width() // 2, 195))

        y = 250
        for line in wrap_lines(desc, SMALL_FONT, 480):
            SCREEN.blit(SMALL_FONT.render(line, True, COLOR_TEXT), (260, y))
            y += 24

        if role == "killer":
            mates = self.lobby.get("teammates", [])
            txt = "Other deviants: " + (", ".join(mates) if mates else "none")
            SCREEN.blit(SMALL_FONT.render(txt, True, COLOR_DEV_RED), (260, y + 10))

        if self.draw_button("Continue", 400, 425, 200, 45):
            self.role_seen = True

    def draw_dead_modal(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        SCREEN.blit(overlay, (0, 0))
        pygame.draw.rect(SCREEN, (12, 22, 36), (230, 190, 540, 250))
        pygame.draw.rect(SCREEN, COLOR_DEV_RED, (230, 190, 540, 250), 2)
        t = TITLE_FONT.render("YOU ARE OUT", True, COLOR_DEV_RED)
        SCREEN.blit(t, (500 - t.get_width() // 2, 210))
        y = 270
        for line in wrap_lines("You were killed or ejected from the house. You can watch "
                               "the game and read the chat, but you can't play anymore.",
                               SMALL_FONT, 480):
            SCREEN.blit(SMALL_FONT.render(line, True, COLOR_TEXT), (260, y))
            y += 24
        if self.draw_button("Continue", 400, 380, 200, 45):
            self.dead_seen = True

    def draw_win(self):
        lob = self.lobby
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        SCREEN.blit(overlay, (0, 0))
        pygame.draw.rect(SCREEN, (12, 22, 36), (200, 90, 600, 470))
        pygame.draw.rect(SCREEN, COLOR_GREEN, (200, 90, 600, 470), 2)

        t = TITLE_FONT.render("ANDROIDS WIN!", True, COLOR_GREEN)
        SCREEN.blit(t, (500 - t.get_width() // 2, 110))
        t = SMALL_FONT.render(lob.get("win_reason") or "The androids won.", True, COLOR_TEXT)
        SCREEN.blit(t, (500 - t.get_width() // 2, 155))
        SCREEN.blit(SMALL_FONT.render("Roles:", True, COLOR_DIM), (230, 200))

        order = {"killer": 0, "detective": 1, "peaceful": 2}
        reveal = sorted(lob.get("reveal", {}).items(), key=lambda kv: order.get(kv[1], 3))
        for i, (name, role) in enumerate(reveal):
            rname, color, _ = ROLE_INFO[role]
            x = 230 + (i % 2) * 280
            y = 228 + (i // 2) * 30
            tag = " (you)" if name == self.user else ""
            SCREEN.blit(SMALL_FONT.render(f"{name}{tag}: {rname}", True, color), (x, y))

        if self.draw_button("Leave", 400, 490, 200, 45):
            self.leave_lobby()

    def draw_lobby(self):
        lob = self.lobby
        if not lob:
            return
        is_host = lob["host"] == self.user

        head = FONT.render(f"Lobby #{lob['code']}", True, COLOR_HUD)
        SCREEN.blit(head, (60, 80))
        hint = FONT.render("Share this code with friends", True, COLOR_DIM)
        SCREEN.blit(hint, (60, 105))

        for i, slot in enumerate(lob["slots"]):
            col = i % 2
            row = i // 2
            px = 60 + col * 250
            py = 150 + row * 60
            pygame.draw.rect(SCREEN, COLOR_DARK_BOX, (px, py, 230, 45))
            border = COLOR_DEV_RED if slot["host"] else COLOR_HUD
            pygame.draw.rect(SCREEN, border, (px, py, 230, 45), 1)
            label = f"[{slot['name']}]" + (" HOST" if slot["host"] else "")
            color = COLOR_DIM if slot["bot"] else COLOR_TEXT
            t = FONT.render(label, True, color)
            SCREEN.blit(t, (px + 12, py + 12))

        pygame.draw.rect(SCREEN, (12, 22, 36), (560, 100, 390, 330))
        pygame.draw.rect(SCREEN, COLOR_HUD, (560, 100, 390, 330), 2)
        title = "Settings" if is_host else "Settings (host only)"
        SCREEN.blit(FONT.render(title, True, COLOR_HUD), (580, 115))

        y = 160
        SCREEN.blit(FONT.render("Players", True, COLOR_TEXT), (580, y + 8))
        if is_host:
            if self.draw_button("6", 800, y, 50, 38, selected=lob["size"] == 6):
                self.change_setting("size", 6)
            if self.draw_button("8", 860, y, 50, 38, selected=lob["size"] == 8):
                self.change_setting("size", 8)
        else:
            SCREEN.blit(FONT.render(str(lob["size"]), True, COLOR_TEXT), (800, y + 8))

        for i, (key, label) in enumerate([("killers", "Killers"),
                                          ("detectives", "Detectives"),
                                          ("quests", "Quests")]):
            y = 220 + i * 60
            SCREEN.blit(FONT.render(label, True, COLOR_TEXT), (580, y + 8))
            if is_host:
                if self.draw_button("-", 800, y, 40, 38):
                    self.change_setting(key, lob[key] - 1)
                SCREEN.blit(FONT.render(str(lob[key]), True, COLOR_TEXT), (858, y + 8))
                if self.draw_button("+", 890, y, 40, 38):
                    self.change_setting(key, lob[key] + 1)
            else:
                SCREEN.blit(FONT.render(str(lob[key]), True, COLOR_TEXT), (800, y + 8))

        if self.lobby_msg:
            m = FONT.render(self.lobby_msg, True, COLOR_DEV_RED)
            SCREEN.blit(m, (560, 445))

        if self.draw_button("Leave", 280, 540, 200, 45):
            self.leave_lobby()

        if is_host:
            if self.draw_button("Start", 520, 540, 200, 45):
                self.start_game()
        else:
            w = FONT.render("Waiting for host...", True, COLOR_DIM)
            SCREEN.blit(w, (520, 553))

    def draw_game(self):
        if not self.lobby:
            return
        lob = self.lobby
        role = lob.get("my_role")
        alive = lob.get("alive", True)
        draw_map()

        if not alive:
            SCREEN.blit(FONT.render("YOU ARE OUT (spectating)", True, COLOR_DEV_RED), (20, 42))
        elif role:
            rname, rcolor, _ = ROLE_INFO[role]
            SCREEN.blit(FONT.render(f"Role: {rname}", True, rcolor), (20, 42))
        SCREEN.blit(SMALL_FONT.render("Click a room to enter", True, COLOR_DIM), (20, 64))
        self.draw_progress()
        self.draw_room_msg(20, 86)

        if lob.get("winner"):
            self.draw_win()
            return
        if lob.get("meeting"):
            self.quest_room = None
            self.kill_room = None
            self.check_open = False
            self.draw_meeting()
            return
        if role and not self.role_seen:
            self.draw_role_modal()
            return
        if not alive:
            self.quest_room = None
            self.kill_room = None
            self.check_open = False
            if not self.dead_seen:
                self.draw_dead_modal()
                return
        if self.quest_room is not None:
            self.draw_quest()
            return
        if self.kill_room is not None:
            self.draw_kill_panel()
            return
        if self.check_open:
            self.draw_check_panel()
            return

        if self.draw_button("Leave", 20, 595, 160, 40):
            self.leave_lobby()
            return

        if role == "detective" and alive:
            label = "Check player" if lob.get("can_check") else "Check used"
            if self.draw_button(label, 790, 595, 190, 40):
                self.check_open = True
                return

        mine_done = lob.get("my_done", [])
        body_rooms = lob.get("body_rooms", [])
        word = "steal" if role == "killer" else "quest"
        mouse = pygame.mouse.get_pos()
        for r in lob["rooms"]:
            if r["id"] not in QUEST_RECTS:
                continue
            rect = mrect(*QUEST_RECTS[r["id"]])
            players = r["players"]
            cap = r["cap"]
            full = len(players) >= cap
            is_done = r["id"] in mine_done
            if is_done:
                color = COLOR_GREEN
            else:
                color = COLOR_DEV_RED if full else COLOR_HUD
            hover = rect.collidepoint(mouse) and not self.exit_confirm
            pygame.draw.rect(SCREEN, color, rect, 4 if hover else 2)

            cnt = FONT.render(f"{len(players)}/{cap}", True, color)
            SCREEN.blit(cnt, (rect.centerx - cnt.get_width() // 2, rect.centery - 34))
            lbl = FONT.render("done" if is_done else word, True,
                              COLOR_GREEN if is_done else COLOR_DIM)
            SCREEN.blit(lbl, (rect.centerx - lbl.get_width() // 2, rect.centery - 14))

            # тени тех, кто внутри
            x0 = rect.centerx - (cap * 26) // 2
            for i in range(cap):
                draw_shadow(x0 + i * 26, rect.centery + 8, i < len(players), color)

            # тело (видят убийцы, выбывшие и те, кто в комнате)
            if r["id"] in body_rooms:
                bx, by = rect.x + 28, rect.y + 28
                pygame.draw.line(SCREEN, COLOR_DEV_RED, (bx - 11, by - 11), (bx + 11, by + 11), 5)
                pygame.draw.line(SCREEN, COLOR_DEV_RED, (bx - 11, by + 11), (bx + 11, by - 11), 5)

            if (self.click_pos and not self.exit_confirm
                    and rect.collidepoint(self.click_pos)):
                self.click_pos = None
                if not alive:
                    self.show_msg("You are out of the game")
                elif role == "killer" and full and self.user not in players:
                    self.kill_room = r["id"]
                else:
                    self.try_enter_room(r["id"])
                break

    def render(self):
        if self.current_screen in ("LOBBY", "GAME"):
            self.poll_lobby()

        SCREEN.fill(COLOR_BG)
        title = TITLE_FONT.render("CYBER-MAFIA", True, COLOR_HUD)
        SCREEN.blit(title, (WIDTH // 2 - title.get_width() // 2, 20))

        if self.user:
            u = FONT.render(f"Player: {self.user}", True, COLOR_TEXT)
            SCREEN.blit(u, (20, 20))

        if self.current_screen == "MAIN":
            if self.draw_button("Create Lobby", 380, 100, 240, 45):
                self.notice = ""
                self.do_create_lobby()

            elif self.draw_button("Join Lobby", 380, 160, 240, 45):
                self.input_code = ""
                self.go("JOIN")

            elif self.draw_button("Log In", 380, 220, 240, 45):
                self.input_user = ""
                self.input_pass = ""
                self.active_field = None
                self.go("LOGIN")

            elif self.draw_button("Customize", 380, 280, 240, 45):
                self.go("CUSTOMIZE")

            elif self.draw_button("Story", 380, 340, 240, 45):
                self.go("STORY")

            elif self.draw_button("Exit", 380, 400, 240, 45):
                self.exit_confirm = True

            if self.notice:
                n = FONT.render(self.notice, True, COLOR_DEV_RED)
                SCREEN.blit(n, (WIDTH // 2 - n.get_width() // 2, 470))

        elif self.current_screen == "LOBBY":
            self.draw_lobby()

        elif self.current_screen == "GAME":
            self.draw_game()

        elif self.current_screen == "JOIN":
            pygame.draw.rect(SCREEN, (12, 22, 36), (300, 150, 400, 300))
            pygame.draw.rect(SCREEN, COLOR_HUD, (300, 150, 400, 300), 2)
            SCREEN.blit(FONT.render("Enter lobby code:", True, COLOR_TEXT), (340, 180))

            pygame.draw.rect(SCREEN, COLOR_ACTIVE, (340, 215, 320, 45))
            pygame.draw.rect(SCREEN, COLOR_HUD, (340, 215, 320, 45), 1)
            code_txt = TITLE_FONT.render(self.input_code, True, COLOR_TEXT)
            SCREEN.blit(code_txt, (350, 220))

            if self.join_msg:
                m = FONT.render(self.join_msg, True, COLOR_DEV_RED)
                SCREEN.blit(m, (340, 275))

            if self.draw_button("Confirm", 400, 315, 200, 45):
                self.do_join()
            elif self.draw_button("Back", 400, 375, 200, 45):
                self.go("MAIN")

        elif self.current_screen == "CUSTOMIZE":
            self.draw_customize()

        elif self.current_screen == "STORY":
            self.draw_story()

        elif self.current_screen == "LOGIN":
            pygame.draw.rect(SCREEN, (12, 22, 36), (300, 150, 400, 360))
            pygame.draw.rect(SCREEN, COLOR_HUD, (300, 150, 400, 360), 2)

            user_box_color = COLOR_ACTIVE if self.active_field == "user" else COLOR_DARK_BOX
            pass_box_color = COLOR_ACTIVE if self.active_field == "pass" else COLOR_DARK_BOX

            pygame.draw.rect(SCREEN, user_box_color, (340, 195, 320, 35))
            pygame.draw.rect(SCREEN, COLOR_HUD, (340, 195, 320, 35), 1)
            pygame.draw.rect(SCREEN, pass_box_color, (340, 255, 320, 35))
            pygame.draw.rect(SCREEN, COLOR_HUD, (340, 255, 320, 35), 1)

            u_txt = FONT.render(f"User: {self.input_user}", True, COLOR_TEXT)
            p_txt = FONT.render(f"Pass: {'*' * len(self.input_pass)}", True, COLOR_TEXT)
            SCREEN.blit(u_txt, (350, 203))
            SCREEN.blit(p_txt, (350, 263))

            if self.login_msg:
                m = FONT.render(self.login_msg, True, COLOR_DEV_RED)
                SCREEN.blit(m, (350, 300))

            if self.draw_button("Confirm", 400, 345, 200, 45):
                self.do_login()
            elif self.draw_button("Back", 400, 405, 200, 45):
                self.go("MAIN")

        if self.exit_confirm:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 150))
            SCREEN.blit(overlay, (0, 0))

            mx, my, mw, mh = 280, 200, 440, 220
            pygame.draw.rect(SCREEN, (8, 14, 22), (mx, my, mw, mh))
            pygame.draw.rect(SCREEN, COLOR_DEV_RED, (mx, my, mw, mh), 2)

            q = FONT.render("Are you sure you want to exit?", True, COLOR_TEXT)
            SCREEN.blit(q, (mx + (mw - q.get_width()) // 2, my + 45))

            if self.draw_button("Yep", mx + 50, my + 120, 140, 45, modal=True):
                pygame.quit()
                sys.exit()
            elif self.draw_button("Nop", mx + 250, my + 120, 140, 45, modal=True):
                self.exit_confirm = False

        self.click_pos = None
        pygame.display.flip()

    # ---------- события ----------
    def handle_login_key(self, event):
        if event.key == pygame.K_TAB:
            self.active_field = "pass" if self.active_field == "user" else "user"
        elif event.key == pygame.K_RETURN:
            self.do_login()
        elif event.key == pygame.K_BACKSPACE:
            if self.active_field == "user":
                self.input_user = self.input_user[:-1]
            elif self.active_field == "pass":
                self.input_pass = self.input_pass[:-1]
        elif event.unicode and event.unicode.isprintable():
            if self.active_field == "user" and len(self.input_user) < 12:
                self.input_user += event.unicode
            elif self.active_field == "pass" and len(self.input_pass) < 32:
                self.input_pass += event.unicode

    def handle_join_key(self, event):
        if event.key == pygame.K_RETURN:
            self.do_join()
        elif event.key == pygame.K_BACKSPACE:
            self.input_code = self.input_code[:-1]
        elif event.unicode.isdigit() and len(self.input_code) < 4:
            self.input_code += event.unicode

    def handle_chat_key(self, event):
        if event.key == pygame.K_RETURN:
            self.send_chat()
        elif event.key == pygame.K_BACKSPACE:
            self.chat_input = self.chat_input[:-1]
        elif event.unicode and event.unicode.isprintable() and len(self.chat_input) < 80:
            self.chat_input += event.unicode

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.click_pos = event.pos
                if self.current_screen == "LOGIN" and not self.exit_confirm:
                    pos = event.pos
                    if 340 <= pos[0] <= 660 and 195 <= pos[1] <= 230:
                        self.active_field = "user"
                    elif 340 <= pos[0] <= 660 and 255 <= pos[1] <= 290:
                        self.active_field = "pass"
                    else:
                        self.active_field = None

            elif event.type == pygame.KEYDOWN and not self.exit_confirm:
                if self.current_screen == "LOGIN":
                    self.handle_login_key(event)
                elif self.current_screen == "JOIN":
                    self.handle_join_key(event)
                elif (self.current_screen == "GAME" and self.lobby
                      and (self.lobby.get("meeting") or {}).get("phase") == "vote"
                      and self.lobby.get("alive", True)):
                    self.handle_chat_key(event)