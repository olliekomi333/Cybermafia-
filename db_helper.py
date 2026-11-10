import sqlite3
import hashlib
import hmac
import os
import threading


class DBHelper:
    def __init__(self, db_name="cybermafia.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.lock = threading.Lock()
        self.create_tables()

    def create_tables(self):
        with self.lock, self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    skin TEXT DEFAULT 'RK800'
                )
            """)

    @staticmethod
    def _hash(password, salt):
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, 100_000
        ).hex()

    def register_or_login(self, username, password):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT password_hash, salt, skin FROM users WHERE username = ?",
                (username,),
            )
            row = cur.fetchone()

            if row:
                pw_hash, salt_hex, skin = row
                check = self._hash(password, bytes.fromhex(salt_hex))
                if hmac.compare_digest(check, pw_hash):
                    return True, skin, "Успешный вход!"
                return False, None, "Неверный пароль!"

            salt = os.urandom(16)
            with self.conn:
                self.conn.execute(
                    "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                    (username, self._hash(password, salt), salt.hex()),
                )
            return True, "RK800", "Аккаунт создан!"

    def update_skin(self, username, skin_name):
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE users SET skin = ? WHERE username = ?", (skin_name, username)
            )