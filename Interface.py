#CODE PALING BENER SUSKS UPDATE ANJAY KELAZZZ
import tkinter as tk
import MySQLdb
import threading

def display_seat_availability():
    # Membuat fungsi untuk memperbarui tampilan
    def update_display():
        # Menghapus semua widget pada window
        for widget in window.winfo_children():
            widget.destroy()

        # Koneksi ke database
        connection = MySQLdb.connect(
            host="127.0.0.1",
            user="root",
            password="",
            database="project"
        )

        # Membuat kursor
        cursor = connection.cursor()

        # Query untuk mengambil jumlah tempat duduk per gerbong
        query = "SELECT gerbong, jumlah_seat FROM trains ORDER BY gerbong"
        cursor.execute(query)

        # Mengambil hasil query
        rows = cursor.fetchall()

        station_frame = tk.LabelFrame(window, text="Stasiun KRL Cisauk", bg="white")
        station_frame.pack(pady=10, padx=10)

        # Satu baris per gerbong
        for gerbong, jumlah_seat in rows:
            carriage_row = tk.Frame(station_frame, bg="white")
            carriage_row.pack(anchor="w", padx=10, pady=2)

            seat_label = tk.Label(carriage_row, text="Gerbong " + str(gerbong) + ":", width=15, anchor="w", bg="white")
            seat_label.pack(side="left")

            if jumlah_seat > 0:
                availability_label = tk.Label(carriage_row, text=jumlah_seat, width=10, anchor="w", relief="solid", bg="green", fg="white")
            else:
                availability_label = tk.Label(carriage_row, text=jumlah_seat, width=10, anchor="w", relief="solid", bg="red", fg="white")

            availability_label.pack(side="left")

        # Menutup kursor dan koneksi database
        cursor.close()
        connection.close()

        # Perbarui tampilan setiap 500 ms
        window.after(500, update_display)

    # Membuat window Tkinter
    window = tk.Tk()
    window.title("Ketersediaan Tempat Duduk")

    # Memulai pembaruan tampilan
    update_display()

    window.mainloop()

# Menampilkan ketersediaan tempat duduk secara real-time
display_seat_availability()
