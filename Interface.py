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
        
        # Query untuk mengambil data tempat duduk
        query = "SELECT * FROM trains"
        cursor.execute(query)
        
        seat_map = {}
        
        # Mengambil hasil query
        rows = cursor.fetchall()
        
        for row in rows:
            carriage = row[1]
            seat = row[2]
            availability = row[3]
            
            if carriage not in seat_map:
                seat_map[carriage] = {}
            
            seat_map[carriage][seat] = availability
        
        for carriage, seats in seat_map.items():
            #carriage_frame = tk.LabelFrame(window, text="Gerbong " + str(carriage), bg="white")
            carriage_frame = tk.LabelFrame(window, text="Stasiun KRL Cisauk" , bg="white")
            carriage_frame.pack(pady=10)
            
            for seat, availability in seats.items():
                seat_label = tk.Label(carriage_frame, text="Gerbong " + seat + ":", width=15, anchor="w", bg="white")
                seat_label.pack(side="left")
                
                if availability > 0:
                    availability_label = tk.Label(carriage_frame, text=availability, width=10, anchor="w", relief="solid", bg="green", fg="white")
                else:
                    availability_label = tk.Label(carriage_frame, text=availability, width=10, anchor="w", relief="solid", bg="red", fg="white")
                
                availability_label.pack(side="left")
            
            separator = tk.Frame(window, height=1, bd=1, relief="groove", bg="white")
            separator.pack(fill="x", padx=10, pady=5)
        
        # Menutup kursor dan koneksi database
        cursor.close()
        connection.close()
        
        # Perbarui tampilan setiap ? detik
        window.after(500, update_display)
    
    # Membuat window Tkinter
    window = tk.Tk()
    window.title("Ketersediaan Tempat Duduk")
    
    # Memulai pembaruan tampilan
    update_display()
    
    window.mainloop()

# Menampilkan ketersediaan tempat duduk secara real-time
display_seat_availability()
