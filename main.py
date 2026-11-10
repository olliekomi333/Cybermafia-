import os
import multiprocessing

NUM_PLAYERS = 2  # כמה משתמשים (חלונות) לפתוח


def run_client(player_num):
    # מיקום שונה לכל חלון כדי שלא יפתחו אחד על השני
    x = 40 + (player_num - 1) * 80
    y = 40 + (player_num - 1) * 60
    os.environ["SDL_VIDEO_WINDOW_POS"] = f"{x},{y}"

    # חשוב: מייבאים את client רק כאן, בתוך התהליך של כל משתמש.
    # client יוצר את החלון כבר בזמן ה-import, אז כל תהליך יקבל חלון משלו.
    import pygame
    from client import CyberClient

    pygame.display.set_caption(f"Cyber-Mafia — Detroit Edition  |  Player {player_num}")

    clock = pygame.time.Clock()
    app = CyberClient()

    while True:
        app.handle_events()
        app.render()
        clock.tick(60)


def main():
    processes = []
    for i in range(1, NUM_PLAYERS + 1):
        p = multiprocessing.Process(target=run_client, args=(i,))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()


if __name__ == "__main__":
    main()