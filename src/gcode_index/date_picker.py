"""Small tkinter calendar popup for DD.MM.YYYY date fields."""

from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date
from tkinter import ttk
from typing import Callable, Optional

from gcode_index.date_format import format_display_date_dmy, parse_display_date

_MONTHS_PL = (
    "",
    "Styczeń",
    "Luty",
    "Marzec",
    "Kwiecień",
    "Maj",
    "Czerwiec",
    "Lipiec",
    "Sierpień",
    "Wrzesień",
    "Październik",
    "Listopad",
    "Grudzień",
)
_WEEKDAYS_PL = ("Pn", "Wt", "Śr", "Cz", "Pt", "So", "Nd")
_WEEKDAYS_EN = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")


class DatePickerDialog(tk.Toplevel):
    """Mini month calendar; picking a day calls ``on_pick(DD.MM.YYYY)`` and closes."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        initial: Optional[str] = None,
        lang: str = "pl",
        on_pick: Optional[Callable[[str], None]] = None,
        title: str = "Calendar",
    ) -> None:
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.grab_set()
        self._on_pick = on_pick
        self._lang = "pl" if str(lang).casefold().startswith("pl") else "en"
        seed = parse_display_date(initial or "") or date.today()
        self._year = seed.year
        self._month = seed.month
        self._selected = seed

        body = ttk.Frame(self, padding=8)
        body.pack(fill=tk.BOTH, expand=True)

        nav = ttk.Frame(body)
        nav.pack(fill=tk.X)
        ttk.Button(nav, text="◀", width=3, command=self._prev_month).pack(side=tk.LEFT)
        self._header = ttk.Label(nav, anchor=tk.CENTER, width=18)
        self._header.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)
        ttk.Button(nav, text="▶", width=3, command=self._next_month).pack(side=tk.RIGHT)

        self._grid = ttk.Frame(body)
        self._grid.pack(fill=tk.BOTH, expand=True, pady=(8, 4))

        btns = ttk.Frame(body)
        btns.pack(fill=tk.X)
        ttk.Button(
            btns,
            text="Today" if self._lang == "en" else "Dziś",
            command=self._pick_today,
        ).pack(side=tk.LEFT)
        ttk.Button(
            btns,
            text="Clear" if self._lang == "en" else "Wyczyść",
            command=self._clear,
        ).pack(side=tk.LEFT, padx=6)
        ttk.Button(
            btns,
            text="Cancel" if self._lang == "en" else "Anuluj",
            command=self.destroy,
        ).pack(side=tk.RIGHT)

        self._day_buttons: list[tk.Button] = []
        self._render()
        self.bind("<Escape>", lambda _e: self.destroy())
        self.after(10, self._place_near_master)

    def _place_near_master(self) -> None:
        try:
            self.update_idletasks()
            mx = self.master.winfo_rootx()
            my = self.master.winfo_rooty() + self.master.winfo_height()
            self.geometry(f"+{mx}+{my}")
        except tk.TclError:
            pass

    def _month_title(self) -> str:
        if self._lang == "pl":
            return f"{_MONTHS_PL[self._month]} {self._year}"
        return f"{calendar.month_name[self._month]} {self._year}"

    def _weekdays(self) -> tuple[str, ...]:
        return _WEEKDAYS_PL if self._lang == "pl" else _WEEKDAYS_EN

    def _prev_month(self) -> None:
        if self._month == 1:
            self._month = 12
            self._year -= 1
        else:
            self._month -= 1
        self._render()

    def _next_month(self) -> None:
        if self._month == 12:
            self._month = 1
            self._year += 1
        else:
            self._month += 1
        self._render()

    def _pick_today(self) -> None:
        self._emit(date.today())

    def _clear(self) -> None:
        if self._on_pick:
            self._on_pick("")
        self.destroy()

    def _emit(self, d: date) -> None:
        if self._on_pick:
            self._on_pick(format_display_date_dmy(d))
        self.destroy()

    def _render(self) -> None:
        for child in self._grid.winfo_children():
            child.destroy()
        self._day_buttons.clear()
        self._header.configure(text=self._month_title())
        for i, name in enumerate(self._weekdays()):
            ttk.Label(self._grid, text=name, width=3, anchor=tk.CENTER).grid(
                row=0, column=i, padx=1, pady=1
            )
        cal = calendar.Calendar(firstweekday=0)  # Monday
        row_i = 1
        today = date.today()
        for week in cal.monthdayscalendar(self._year, self._month):
            for col, day in enumerate(week):
                if day == 0:
                    ttk.Label(self._grid, text="", width=3).grid(
                        row=row_i, column=col, padx=1, pady=1
                    )
                    continue
                d = date(self._year, self._month, day)
                is_sel = d == self._selected
                is_today = d == today
                bg = "#0d6e4f" if is_sel else ("#e8f5ef" if is_today else "#f5f5f5")
                fg = "#ffffff" if is_sel else "#222222"
                btn = tk.Button(
                    self._grid,
                    text=str(day),
                    width=3,
                    relief=tk.FLAT,
                    bg=bg,
                    fg=fg,
                    activebackground="#095c42",
                    activeforeground="#ffffff",
                    command=lambda dd=d: self._emit(dd),
                )
                btn.grid(row=row_i, column=col, padx=1, pady=1)
                self._day_buttons.append(btn)
            row_i += 1


def open_date_picker(
    master: tk.Misc,
    var: tk.Variable,
    *,
    lang: str = "pl",
    title: str = "Calendar",
) -> None:
    """Open a calendar popup bound to ``var`` (StringVar of DD.MM.YYYY)."""

    def _apply(value: str) -> None:
        var.set(value)

    DatePickerDialog(
        master,
        initial=str(var.get() or ""),
        lang=lang,
        on_pick=_apply,
        title=title,
    )
