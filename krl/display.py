"""Full-screen seat availability board for a station screen.

Usage:
    uv run python -m krl.display              # windowed
    uv run python -m krl.display --fullscreen # press Escape to leave full screen
"""

import argparse
import logging
import time
import tkinter as tk

from sqlalchemy.exc import SQLAlchemyError

from krl import db
from krl.config import load_settings

REFRESH_MS = 500
STATION_NAME = "Stasiun KRL Cisauk"
LOW_SEATS = 6  # at or below this many free seats, the card is amber

BACKGROUND = "#F3F4F6"
CARD = "#FFFFFF"
BORDER = "#D1D5DB"
TEXT = "#111827"
MUTED = "#6B7280"
ERROR = "#B91C1C"
STATUS_COLOUR = {"ok": "#15803D", "low": "#B45309", "full": "#B91C1C"}

log = logging.getLogger("krl.display")


def seat_status(seats):
    if seats <= 0:
        return "full"
    if seats <= LOW_SEATS:
        return "low"
    return "ok"


class SeatBoard:
    def __init__(self, root, engine):
        self.root = root
        self.engine = engine
        self.cards = {}  # gerbong -> dict of the card's widgets
        self.last_ok = None

        root.title("Ketersediaan Tempat Duduk")
        root.configure(bg=BACKGROUND)
        root.bind("<Escape>", lambda _event: root.attributes("-fullscreen", False))

        page = tk.Frame(root, bg=BACKGROUND)
        page.pack(expand=True, fill="both", padx=48, pady=32)

        tk.Label(page, text=STATION_NAME, font=("Helvetica", 34, "bold"), fg=TEXT, bg=BACKGROUND).pack()
        tk.Label(page, text="Ketersediaan tempat duduk", font=("Helvetica", 16), fg=MUTED, bg=BACKGROUND).pack(pady=(0, 36))

        self.cards_frame = tk.Frame(page, bg=BACKGROUND)
        self.cards_frame.pack(expand=True)

        self.footer = tk.Label(page, text="", font=("Helvetica", 13), fg=MUTED, bg=BACKGROUND)
        self.footer.pack(pady=(36, 0))

        self.refresh()

    def refresh(self):
        try:
            seats = db.read_seats(self.engine)
        except SQLAlchemyError as error:
            log.warning("Could not read seat counts: %s", error)
            self.show_offline()
        else:
            self.last_ok = time.time()
            self.show(seats)
            self.footer.config(text=f"Diperbarui {time.strftime('%H:%M:%S', time.localtime(self.last_ok))}", fg=MUTED)
        self.root.after(REFRESH_MS, self.refresh)

    def show_offline(self):
        # Keep the last known numbers on screen, but say they may be out of date
        message = "Data tidak tersedia"
        if self.last_ok:
            message += f". Terakhir diperbarui {time.strftime('%H:%M:%S', time.localtime(self.last_ok))}"
        self.footer.config(text=message, fg=ERROR)

    def show(self, seats):
        gerbongs = [gerbong for gerbong, _ in seats]
        if gerbongs != list(self.cards):
            self.build_cards(gerbongs)
        for gerbong, free in seats:
            self.update_card(gerbong, free)

    def build_cards(self, gerbongs):
        for widget in self.cards_frame.winfo_children():
            widget.destroy()
        self.cards = {}
        for column, gerbong in enumerate(gerbongs):
            card = tk.Frame(self.cards_frame, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
            card.grid(row=0, column=column, padx=14)

            strip = tk.Frame(card, bg=CARD, height=8)
            strip.pack(fill="x")
            body = tk.Frame(card, bg=CARD, padx=36, pady=24)
            body.pack()

            title = tk.Label(body, text=f"Gerbong {gerbong}", font=("Helvetica", 18), fg=MUTED, bg=CARD)
            title.pack()
            number = tk.Label(body, text="", font=("Helvetica", 72, "bold"), bg=CARD)
            number.pack()
            caption = tk.Label(body, text="", font=("Helvetica", 16), fg=MUTED, bg=CARD)
            caption.pack()

            self.cards[gerbong] = {"strip": strip, "number": number, "caption": caption}

    def update_card(self, gerbong, free):
        card = self.cards[gerbong]
        colour = STATUS_COLOUR[seat_status(free)]
        card["strip"].config(bg=colour)
        card["number"].config(text=str(max(free, 0)), fg=colour)
        card["caption"].config(text="penuh" if free <= 0 else "kursi kosong")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fullscreen", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    settings = load_settings()
    engine = db.make_engine(settings)
    root = tk.Tk()
    if args.fullscreen:
        root.attributes("-fullscreen", True)
    SeatBoard(root, engine)
    root.mainloop()


if __name__ == "__main__":
    main()
