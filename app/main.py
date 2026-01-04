# app/main.py
import tkinter as tk
from tkinter import ttk

from app.ui.main_window import MainWindow


def main() -> None:
    root = tk.Tk()
    root.title("Home Finance Centre")
    root.geometry("850x600")

    ttk.Style().theme_use("clam")

    MainWindow(root).pack(fill="both", expand=True)
    root.mainloop()


if __name__ == "__main__":
    main()
