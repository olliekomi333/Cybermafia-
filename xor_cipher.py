import base64


class XORCipher:
    """Шифрование и расшифровка методом XOR с повторяющимся ключом.

    XOR симметричен: одна и та же операция и шифрует, и расшифровывает.
    Для текста результат кодируется в base64, чтобы его можно было
    безопасно отправлять по сети внутри JSON.
    """

    def __init__(self, key="CyberMafia"):
        if not key:
            raise ValueError("Ключ не может быть пустым")
        self.key = key.encode("utf-8")

    # ---------- байты ----------
    def _xor(self, data: bytes) -> bytes:
        key = self.key
        n = len(key)
        return bytes(b ^ key[i % n] for i, b in enumerate(data))

    def encrypt_bytes(self, data: bytes) -> bytes:
        """Зашифровать байты."""
        return self._xor(data)

    def decrypt_bytes(self, data: bytes) -> bytes:
        """Расшифровать байты."""
        return self._xor(data)

    # ---------- текст ----------
    def encrypt(self, text: str) -> str:
        """Зашифровать строку. Возвращает строку base64."""
        raw = self._xor(text.encode("utf-8"))
        return base64.b64encode(raw).decode("ascii")

    def decrypt(self, token: str) -> str:
        """Расшифровать строку base64, полученную из encrypt()."""
        raw = base64.b64decode(token.encode("ascii"))
        return self._xor(raw).decode("utf-8")


if __name__ == "__main__":
    cipher = XORCipher("secret")
    original = '{"action": "login", "username": "Ollie", "password": "123"}'
    encrypted = cipher.encrypt(original)
    decrypted = cipher.decrypt(encrypted)
    print("Оригинал:    ", original)
    print("Шифр:        ", encrypted)
    print("Расшифровано:", decrypted)
    print("Совпадает:   ", decrypted == original)