import pygame
import sys
import socket
import json

pygame.init()
WIDTH, HEIGHT = 1000, 650
SCREEN = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Cyber-Mafia — Detroit Edition")
FONT = pygame.font.SysFont("Consolas", 18, bold=True)
TITLE_FONT = pygame.font.SysFont("Consolas", 32, bold=True)

COLOR_BG = (10, 16, 26)
COLOR_HUD = (0, 212, 255)
COLOR_TEXT = (220, 245, 255)
COLOR_DIM = (110, 140, 160)
COLOR_DARK_BOX = (15, 28, 44)
COLOR_DEV_RED = (255, 40, 80)
COLOR_ACTIVE = (0, 80, 120)


class CyberClient:
    def __init__(self):
        self.sock = None
        self.connected = False
        self.rbuf = b""

        self.current_screen = "MAIN"
        self.user = ""
        self.skin = "RK800"
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
        self.user = ""      # на сервере сессия потеряна
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
        self.notice = ""
        self.login_msg = ""
        self.join_msg = ""
        self.lobby_msg = ""

    def connection_lost(self):
        self.go("MAIN")
        self.notice = "Связь с сервером потеряна!"

    # ---------- логика ----------
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
            self.go("MAIN")
        else:
            self.login_msg = res.get("msg", "Ошибка входа")

    def do_create_lobby(self):
        if not self.user:
            self.notice = "Сначала войдите (Log In)!"
            return
        res = self.send_request({"action": "create_lobby"})
        if res is None:
            self.connection_lost()
        elif res.get("status"):
            self.lobby = res["lobby"]
            self.go("LOBBY")
            self.last_poll = pygame.time.get_ticks()
        else:
            self.notice = res.get("msg", "Ошибка")

    def do_join(self):
        code = self.input_code.strip()
        if len(code) != 4:
            self.join_msg = "Код — 4 цифры!"
            return
        res = self.send_request({"action": "join_lobby", "code": code})
        if res is None:
            self.connection_lost()
        elif res.get("status"):
            self.lobby = res["lobby"]
            self.go("LOBBY")
            self.last_poll = pygame.time.get_ticks()
        else:
            self.join_msg = res.get("msg", "Ошибка")

    def leave_lobby(self):
        self.send_request({"action": "leave_lobby"})
        self.lobby = None
        self.go("MAIN")

    def apply_lobby_response(self, res):
        if res is None:
            self.connection_lost()
        elif res.get("status"):
            self.lobby = res["lobby"]
            self.lobby_msg = ""
        elif res.get("closed"):
            self.lobby = None
            self.go("MAIN")
            self.notice = res.get("msg", "Лобби закрыто")
        else:
            self.lobby_msg = res.get("msg", "Ошибка")

    def poll_lobby(self):
        now = pygame.time.get_ticks()
        if now - self.last_poll > 1000:
            self.last_poll = now
            self.apply_lobby_response(self.send_request({"action": "get_lobby"}))

    def change_setting(self, key, value):
        if not self.lobby or self.lobby["host"] != self.user:
            return
        settings = {k: self.lobby[k] for k in ("size", "killers", "detectives", "quests")}
        settings[key] = value
        res = self.send_request({"action": "update_settings", **settings})
        self.apply_lobby_response(res)

    # ---------- рисование ----------
    def draw_button(self, text, x, y, w, h, modal=False, selected=False):
        """Рисует кнопку. Возвращает True, если по ней кликнули в этом кадре."""
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

    def draw_android_2d(self, x, y):
        pygame.draw.ellipse(SCREEN, COLOR_HUD, (x - 60, y + 160, 120, 30), 2)
        pygame.draw.line(SCREEN, COLOR_TEXT, (x, y), (x, y + 100), 4)
        pygame.draw.circle(SCREEN, COLOR_TEXT, (x, y - 20), 18, 2)
        pygame.draw.circle(SCREEN, COLOR_HUD, (x + 12, y - 24), 4)
        pygame.draw.line(SCREEN, COLOR_TEXT, (x, y + 30), (x - 30, y + 70), 3)
        pygame.draw.line(SCREEN, COLOR_TEXT, (x, y + 30), (x + 30, y + 70), 3)
        pygame.draw.line(SCREEN, COLOR_TEXT, (x, y + 100), (x - 25, y + 160), 3)
        pygame.draw.line(SCREEN, COLOR_TEXT, (x, y + 100), (x + 25, y + 160), 3)

    def draw_lobby(self):
        lob = self.lobby
        if not lob:
            return
        is_host = lob["host"] == self.user

        head = FONT.render(f"Lobby #{lob['code']}", True, COLOR_HUD)
        SCREEN.blit(head, (60, 80))
        hint = FONT.render("Share this code with friends", True, COLOR_DIM)
        SCREEN.blit(hint, (60, 105))

        # слоты игроков
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

        # панель настроек
        pygame.draw.rect(SCREEN, (12, 22, 36), (560, 100, 390, 330))
        pygame.draw.rect(SCREEN, COLOR_HUD, (560, 100, 390, 330), 2)
        title = "Settings" if is_host else "Settings (host only)"
        SCREEN.blit(FONT.render(title, True, COLOR_HUD), (580, 115))

        # игроки: 6 / 8
        y = 160
        SCREEN.blit(FONT.render("Players", True, COLOR_TEXT), (580, y + 8))
        if is_host:
            if self.draw_button("6", 800, y, 50, 38, selected=lob["size"] == 6):
                self.change_setting("size", 6)
            if self.draw_button("8", 860, y, 50, 38, selected=lob["size"] == 8):
                self.change_setting("size", 8)
        else:
            SCREEN.blit(FONT.render(str(lob["size"]), True, COLOR_TEXT), (800, y + 8))

        # убийцы / детективы / квесты
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

        if self.draw_button("Leave", 400, 540, 200, 45):
            self.leave_lobby()

    def render(self):
        if self.current_screen == "LOBBY":
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
                if not self.user:
                    self.notice = "Сначала войдите (Log In)!"
                else:
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
            self.draw_android_2d(250, 250)
            for r in range(3):
                for c in range(3):
                    bx = 500 + c * 80
                    by = 180 + r * 80
                    pygame.draw.rect(SCREEN, COLOR_DARK_BOX, (bx, by, 70, 70))
                    pygame.draw.rect(SCREEN, COLOR_HUD, (bx, by, 70, 70), 1)

            if self.draw_button("Back", 400, 520, 200, 45):
                self.go("MAIN")

        elif self.current_screen == "STORY":
            story_txt = [
                "Detroit 2038. Androids have awakened.",
                "Deviants walk among humans undetected.",
                "Identify the imposter before CyberLife shuts down the sector."
            ]
            for i, line in enumerate(story_txt):
                t = FONT.render(line, True, COLOR_TEXT)
                SCREEN.blit(t, (150, 150 + i * 40))

            if self.draw_button("Back", 400, 480, 200, 45):
                self.go("MAIN")

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

        # Окно подтверждения выхода
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