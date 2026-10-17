"""Full-screen seat availability board for a station screen.

Usage:
    python -m krl.display              # windowed
    python -m krl.display --fullscreen # press Escape to leave full screen
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
GREEN = "#1b7f3b"
AMBER = "#c77700"
RED = "#b3261e"
GREY = "#6b6b6b"
MIN_AMBER_SEATS = 6

log = logging.getLogger("krl.display")


def seat_colour(seats):
    if seats <= 0:
        return RED
    if seats < MIN_AMBER_SEATS:
        return AMBER
    return GREEN


class SeatBoard:
    def __init__(self, root, engine):
        self.root = root
        self.engine = engine
        self.rows = {}  # gerbong -> (name label, seats label)
        self.last_ok = None

        root.title("Ketersediaan Tempat Duduk")
        root.configure(bg="white")
        root.bind("<Escape>", lambda _event: root.attributes("-fullscreen", False))

        self.status = tk.Label(root, text="", font=("Helvetica", 18, "bold"), fg=RED, bg="white")
        self.status.pack(pady=(20, 0))
        self.board = tk.LabelFrame(root, text=STATION_NAME, font=("Helvetica", 22), bg="white", padx=20, pady=10)
        self.board.pack(padx=40, pady=30)

        self.refresh()

    def refresh(self):
        try:
            seats = db.read_seats(self.engine)
        except SQLAlchemyError as error:
            log.warning("Could not read seat counts: %s", error)
            since = time.strftime("%H:%M:%S", time.localtime(self.last_ok)) if self.last_ok else "-"
            self.status.config(text=f"Data tidak tersedia (terakhir diperbarui {since})")
        else:
            self.last_ok = time.time()
            self.status.config(text="")
            self.show(seats)
        self.root.after(REFRESH_MS, self.refresh)

    def show(self, seats):
        # Rebuild the rows only when the carriages change; otherwise update labels in place (no flicker)
        gerbongs = [gerbong for gerbong, _ in seats]
        if gerbongs != list(self.rows):
            for widget in self.board.winfo_children():
                widget.destroy()
            self.rows = {}
            for gerbong in gerbongs:
                row = tk.Frame(self.board, bg="white")
                row.pack(anchor="w", pady=6)
                name = tk.Label(row, text=f"Gerbong {gerbong}", width=12, anchor="w", font=("Helvetica", 22), bg="white")
                name.pack(side="left")
                value = tk.Label(row, width=12, anchor="center", font=("Helvetica", 22, "bold"), fg="white")
                value.pack(side="left", padx=10)
                self.rows[gerbong] = (name, value)

        for gerbong, seats_free in seats:
            _, value = self.rows[gerbong]
            if seats_free <= 0:
                value.config(text="PENUH", bg=RED)
            else:
                value.config(text=f"{seats_free} kursi", bg=seat_colour(seats_free))


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
