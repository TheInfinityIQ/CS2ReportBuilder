"""Hoverable season roster list, with per-account explanations and stable IDs."""
import tkinter as tk

BG = '#15212d'
MUTED = '#a5b3bf'


class RosterHint:
    def __init__(self, anchor):
        self.anchor = anchor
        self.data = None
        self.window = self.detail = None
        self.show_timer = self.hide_timer = None
        anchor.bind('<Enter>', self.schedule, add='+')
        anchor.bind('<Leave>', self.leave, add='+')
        anchor.bind('<FocusIn>', self.schedule, add='+')
        anchor.bind('<FocusOut>', self.leave, add='+')
        anchor.bind('<Destroy>', lambda _: self.close(), add='+')

    def set(self, data):
        self.close()
        self.data = data

    def schedule(self, _=None):
        if self.show_timer:
            self.anchor.after_cancel(self.show_timer)
        if self.hide_timer:
            self.anchor.after_cancel(self.hide_timer)
            self.hide_timer = None
        self.show_timer = self.anchor.after(250, self.show)

    def leave(self, _=None):
        if self.show_timer:
            self.anchor.after_cancel(self.show_timer)
            self.show_timer = None
        if self.hide_timer:
            self.anchor.after_cancel(self.hide_timer)
        self.hide_timer = self.anchor.after(250, self.hide_if_outside)

    def hide_if_outside(self):
        self.hide_timer = None
        x, y = self.anchor.winfo_pointerxy()
        for widget in (self.anchor, self.window, self.detail):
            if widget and widget.winfo_exists() and widget.winfo_rootx() <= x < widget.winfo_rootx() + widget.winfo_width() and widget.winfo_rooty() <= y < widget.winfo_rooty() + widget.winfo_height():
                self.leave()
                return
        self.close()

    def close(self):
        for timer in (self.show_timer, self.hide_timer):
            if timer:
                try:
                    self.anchor.after_cancel(timer)
                except tk.TclError:
                    pass
        self.show_timer = self.hide_timer = None
        for window in (self.detail, self.window):
            if window:
                try:
                    window.destroy()
                except tk.TclError:
                    pass
        self.detail = self.window = None

    def show(self):
        self.show_timer = None
        if self.window or not self.data:
            return
        self.window = window = tk.Toplevel(self.anchor)
        window.wm_overrideredirect(True)
        window.configure(bg=BG, highlightbackground='#40576b', highlightthickness=1)
        tk.Label(window, text=f"S{self.data['selected']} → latest S{self.data['latest']}", bg=BG,
                 fg='#edf3f8', font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=12, pady=(10, 4))
        tk.Label(window, text='Changes from the selected season to the latest season.\nHover a name for its meaning and account IDs.',
                 bg=BG, fg=MUTED, font=('Segoe UI', 9), justify='left', wraplength=400).pack(anchor='w', padx=12)
        body = tk.Frame(window, bg=BG)
        body.pack(fill='both', expand=True, padx=8, pady=6)
        canvas = tk.Canvas(body, bg=BG, width=390, height=min(420, 90 + len(self.data['items']) * 26), highlightthickness=0)
        canvas.pack(side='left', fill='both', expand=True)
        scroll = tk.Scrollbar(body, command=canvas.yview)
        scroll.pack(side='right', fill='y')
        canvas.configure(yscrollcommand=scroll.set)
        rows = tk.Frame(canvas, bg=BG)
        canvas.create_window((0, 0), window=rows, anchor='nw')
        for role, title in [('main', '--- Main Roster ---'), ('sub', '--- Subs ---'), ('unknown', '--- Historical roles unverified ---')]:
            members = [p for p in self.data['items'] if p.get('role', 'unknown') == role]
            if not members and role == 'unknown':
                continue
            tk.Label(rows, text=title, bg=BG, fg=MUTED, font=('Segoe UI', 9, 'bold')).pack(anchor='w', padx=4, pady=(8, 3))
            for player in members:
                row = tk.Label(rows, text=f"{player['prefix']} {player['nickname']}", bg=BG,
                               fg=player['color'], font=('Segoe UI', 10), cursor='question_arrow')
                row.pack(anchor='w', padx=8, pady=2)
                row.bind('<Enter>', lambda event, item=player: self.explain(event.widget, item))
                row.bind('<Leave>', lambda _: self.hide_detail())
            if not members:
                tk.Label(rows, text='No verified names available.', bg=BG, fg=MUTED, font=('Segoe UI', 9)).pack(anchor='w', padx=8)
        rows.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox('all'))
        tk.Label(window, text=self.data['basis_note'], bg=BG, fg='#e2bc78', font=('Segoe UI', 9),
                 justify='left', wraplength=400).pack(anchor='w', padx=12, pady=(3, 10))
        window.bind('<Enter>', self.schedule, add='+')
        window.bind('<Leave>', self.leave, add='+')
        def scroll_roster(event):
            canvas.yview_scroll(-int(event.delta / 120), 'units')
            return 'break'
        window.bind('<MouseWheel>', scroll_roster)
        window.update_idletasks()
        x = min(self.anchor.winfo_rootx(), self.anchor.winfo_screenwidth() - window.winfo_reqwidth() - 12)
        y = min(self.anchor.winfo_rooty() + self.anchor.winfo_height() + 6,
                self.anchor.winfo_screenheight() - window.winfo_reqheight() - 35)
        window.geometry(f'+{max(0, x)}+{max(0, y)}')

    def hide_detail(self):
        if self.detail:
            try:
                self.detail.destroy()
            except tk.TclError:
                pass
            self.detail = None

    def explain(self, row, player):
        self.hide_detail()
        self.detail = detail = tk.Toplevel(self.window)
        detail.wm_overrideredirect(True)
        detail.configure(bg='#213345', highlightbackground='#58768e', highlightthickness=1)
        text = player['description'] + '\n\nFACEIT account ID: ' + player['player_id']
        if player.get('steam_id64'):
            text += '\nSteamID64: ' + player['steam_id64']
        tk.Label(detail, text=text, bg='#213345', fg='#edf3f8', font=('Segoe UI', 9),
                 justify='left', wraplength=390, padx=10, pady=8).pack()
        detail.update_idletasks()
        x = min(row.winfo_rootx() + 80, row.winfo_screenwidth() - detail.winfo_reqwidth() - 12)
        y = min(row.winfo_rooty() + row.winfo_height() + 3, row.winfo_screenheight() - detail.winfo_reqheight() - 35)
        detail.geometry(f'+{max(0, x)}+{max(0, y)}')
