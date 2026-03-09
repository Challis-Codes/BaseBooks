import customtkinter as ctk
import sqlite3
import requests
import threading
import certifi
import os
from tkinter import messagebox, ttk
import tkinter as tk
from datetime import datetime, date

os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DB_PATH = os.path.expanduser("~/Bookstore/bookstore.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

DAYS = {0: "Monday", 1: "Tuesday", 2: "Wednesday",
        3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}

MONTHS = {1: "January", 2: "February", 3: "March", 4: "April",
          5: "May", 6: "June", 7: "July", 8: "August",
          9: "September", 10: "October", 11: "November", 12: "December"}

COLLECTIBLE_GENRES = {"Collectibles/Specialty", "Collectibles", "Specialty",
                      "Collectibles & Specialty"}

MONTH_NAMES = ["January","February","March","April","May","June",
               "July","August","September","October","November","December"]

YEAR_RANGE = [str(y) for y in range(2024, 2035)]

# Genre list is now stored in the DB — see get_all_genres() / ensure_genre()


# ── Searchable Genre Widget ───────────────────────────────────────────────────
class GenreEntry(ctk.CTkFrame):
    """
    Searchable genre input. Type to filter, scroll/click to select.
    Custom values allowed — just type and leave the field.
    API: .get()  .set(value)  .configure_border(valid)
    """
    ROW_HEIGHT = 28
    VISIBLE_ROWS = 5

    def __init__(self, master, width=220, **kwargs):
        super().__init__(master, fg_color="transparent", width=width, **kwargs)
        self._width = width
        self._dropdown_open = False
        self._listbox = None
        self._toplevel = None
        self._filtered = []
        self._hover_index = -1
        self._close_after_id = None

        self._var = ctk.StringVar()
        self._var.trace_add("write", self._on_type)

        self._entry = ctk.CTkEntry(self, textvariable=self._var,
                                   width=width, placeholder_text="Type to search…")
        self._entry.pack(fill="x")

        # Populate from DB on first open; refreshed each time dropdown opens
        self._all_genres = []
        self._reload_genres()

        self._entry.bind("<FocusIn>",  self._on_focus_in)
        self._entry.bind("<FocusOut>", self._on_focus_out)
        self._entry.bind("<Return>",   self._on_enter)
        self._entry.bind("<Down>",     self._on_down)
        self._entry.bind("<Up>",       self._on_up)
        self._entry.bind("<Escape>",   self._close_dropdown)

    # ── Public API ────────────────────────────────────────────────────────────
    def get(self):
        return self._var.get().strip()

    def set(self, value):
        self._var.set(value or "")

    def configure_border(self, valid):
        highlight_required(self._entry, valid)

    def focus_set(self):
        self._entry.focus_set()

    # ── Internal ──────────────────────────────────────────────────────────────
    def _on_type(self, *_):
        query = self._var.get().strip().lower()
        if query:
            self._filtered = [g for g in self._all_genres if query in g.lower()]
        else:
            self._filtered = list(self._all_genres)
        self._hover_index = -1
        if self._filtered:
            self._open_dropdown()
        else:
            self._close_dropdown()

    def _reload_genres(self):
        try:
            self._all_genres = get_all_genres()
        except Exception:
            self._all_genres = []

    def _on_focus_in(self, _=None):
        self._reload_genres()
        self._on_type()

    def _on_focus_out(self, _=None):
        self._close_after_id = self.after(200, self._close_dropdown)

    def _on_enter(self, _=None):
        if 0 <= self._hover_index < len(self._filtered):
            self._select(self._filtered[self._hover_index])
        else:
            self._close_dropdown()

    def _on_down(self, _=None):
        if not self._dropdown_open:
            self._open_dropdown()
            return
        self._hover_index = min(self._hover_index + 1, len(self._filtered) - 1)
        self._refresh_highlight()
        self._scroll_to_hover()

    def _on_up(self, _=None):
        self._hover_index = max(self._hover_index - 1, 0)
        self._refresh_highlight()
        self._scroll_to_hover()

    def _open_dropdown(self):
        if not self._filtered:
            return
        self._close_dropdown(destroy=True)
        self._dropdown_open = True

        x = self._entry.winfo_rootx()
        y = self._entry.winfo_rooty() + self._entry.winfo_height() + 2
        h = min(len(self._filtered), self.VISIBLE_ROWS) * self.ROW_HEIGHT + 4

        self._toplevel = tk.Toplevel(self)
        self._toplevel.wm_overrideredirect(True)
        self._toplevel.wm_geometry(f"{self._width}x{h}+{x}+{y}")
        self._toplevel.configure(bg="#2b2b2b")
        self._toplevel.attributes("-topmost", True)

        frame = tk.Frame(self._toplevel, bg="#2b2b2b")
        frame.pack(fill="both", expand=True)

        scrollbar = tk.Scrollbar(frame, orient="vertical", bg="#3a3a3a",
                                  troughcolor="#2b2b2b", width=10)
        self._listbox = tk.Listbox(
            frame,
            yscrollcommand=scrollbar.set,
            bg="#2b2b2b", fg="white",
            selectbackground="#1f538d", selectforeground="white",
            activestyle="none",
            highlightthickness=1,
            highlightcolor="#1f538d",
            highlightbackground="#3a3a3a",
            borderwidth=0,
            font=("Segoe UI", 11),
            height=self.VISIBLE_ROWS,
        )
        scrollbar.config(command=self._listbox.yview)
        self._listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for genre in self._filtered:
            self._listbox.insert("end", f"  {genre}")

        self._listbox.bind("<Button-1>",   self._on_click)
        self._listbox.bind("<Motion>",     self._on_mouse_move)

        def _scroll(e):
            if self._listbox:
                self._listbox.yview_scroll(-1 if e.delta > 0 else 1, "units")

        # bind_all catches scroll events even when the overrideredirect
        # toplevel doesn't receive native focus on macOS
        self._toplevel.bind_all("<MouseWheel>", _scroll)
        self._toplevel.bind("<Destroy>",
                            lambda e: self._toplevel.unbind_all("<MouseWheel>")
                            if e.widget is self._toplevel else None)

    def _close_dropdown(self, _=None, destroy=False):
        if self._close_after_id:
            self.after_cancel(self._close_after_id)
            self._close_after_id = None
        self._dropdown_open = False
        self._hover_index = -1
        if self._toplevel:
            try:
                self._toplevel.destroy()
            except Exception:
                pass
            self._toplevel = None
            self._listbox = None

    def _select(self, genre):
        self._var.set(genre)
        self._close_dropdown()
        self._entry.icursor("end")
        ensure_genre(genre)

    def _on_click(self, event):
        if self._close_after_id:
            self.after_cancel(self._close_after_id)
            self._close_after_id = None
        idx = self._listbox.nearest(event.y)
        if 0 <= idx < len(self._filtered):
            self._select(self._filtered[idx])

    def _on_mouse_move(self, event):
        idx = self._listbox.nearest(event.y)
        if idx != self._hover_index:
            self._hover_index = idx
            self._refresh_highlight()

    def _refresh_highlight(self):
        if not self._listbox:
            return
        self._listbox.selection_clear(0, "end")
        if 0 <= self._hover_index < len(self._filtered):
            self._listbox.selection_set(self._hover_index)

    def _scroll_to_hover(self):
        if self._listbox and 0 <= self._hover_index < len(self._filtered):
            self._listbox.see(self._hover_index)


# ── Database Setup ────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no  INTEGER UNIQUE NOT NULL,
            isbn        TEXT,
            title       TEXT NOT NULL,
            author      TEXT,
            genre       TEXT,
            price       REAL,
            location    TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            name               TEXT NOT NULL,
            phone              TEXT,
            email              TEXT,
            deros_date         TEXT,
            preferred_contact  TEXT,
            social_handle      TEXT,
            store_credit       REAL DEFAULT 0.0,
            collectible_credit REAL DEFAULT 0.0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS credit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            date        TEXT NOT NULL,
            amount      REAL NOT NULL,
            credit_type TEXT DEFAULT 'regular',
            note        TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS special_sales (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            genre      TEXT NOT NULL,
            pct        REAL NOT NULL,
            start_date TEXT NOT NULL,
            end_date   TEXT NOT NULL,
            note       TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            date           TEXT NOT NULL,
            customer_id    INTEGER,
            subtotal       REAL,
            discount_total REAL,
            total          REAL,
            payment_cash   REAL DEFAULT 0,
            payment_card   REAL DEFAULT 0,
            payment_credit REAL DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sale_items (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id      INTEGER NOT NULL,
            invoice_no   INTEGER,
            title        TEXT,
            genre        TEXT,
            orig_price   REAL,
            discount_pct REAL DEFAULT 0,
            final_price  REAL,
            FOREIGN KEY (sale_id) REFERENCES sales(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS do_not_take (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            type        TEXT NOT NULL,
            value       TEXT NOT NULL,
            note        TEXT,
            do_not_take INTEGER NOT NULL DEFAULT 1
        )
    """)
    try:
        c.execute("ALTER TABLE do_not_take ADD COLUMN do_not_take INTEGER NOT NULL DEFAULT 1")
    except Exception:
        pass

    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_discounts (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            day_num  INTEGER NOT NULL,
            day_name TEXT NOT NULL,
            genre    TEXT NOT NULL,
            pct      REAL NOT NULL DEFAULT 25
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS monthly_discounts (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            month_num INTEGER NOT NULL,
            genre     TEXT NOT NULL,
            pct       REAL NOT NULL DEFAULT 25
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS genres (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS wants (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            title       TEXT,
            author      TEXT,
            isbn        TEXT,
            notes       TEXT,
            date_added  TEXT NOT NULL DEFAULT (date('now')),
            fulfilled   INTEGER NOT NULL DEFAULT 0
        )
    """)

    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('last_invoice', '0')")

    # Seed DNT list if empty
    c.execute("SELECT COUNT(*) FROM do_not_take")
    if c.fetchone()[0] == 0:
        _DNT_SEED = [
            ('category','Homeschool curriculum','Includes teaching guides, workbooks, answer keys',1),
            ('category','Textbooks/course guides','Except recently published HS/college prep and military testing',1),
            ('category','Star Trek / CSI series','TV/Movie Novelizations — exception: Superhero/Game',1),
            ('category','Dover Thrift Editions','',1),('category','Skinny romance / Harlequin','',1),
            ('category','Chicken Soup for the Soul series','',1),('category','What to Expect When series','',1),
            ('category','Gift books (#1 Mom/Dad etc.)','',1),('category','Not-for-resale / free book club copies','',1),
            ('category','Advanced Reader Copies (ARCs)','',1),('category','Coffee Table Books','',1),
            ('category','Music Sheets','',1),
            ('category','Books without dust jacket','UNLESS popular or classic',1),
            ('category','Heavily damaged books','Stickered, water damaged, stained, or heavily written in',1),
            ('category','Self-help (older)','Must be published within last 3 years OR beloved classic',1),
            ('category','Religion (older)','Must be published within last 3 years OR beloved classic',1),
            ('category','Movie novelizations (Kids)','',1),('category','Books in foreign languages (Kids)','',1),
            ('category','Happy Meal / Chick-Fil-A books','',1),
            ('category','Leap Frog / Me Reader','Unless comes with everything including electronic',1),
            ('category','Incomplete book sets','',1),('category','Old Nickelodeon series','',1),
            ('title','Arthur','Kids/Teen series — do not take',1),('title','Dora the Explorer','Kids/Teen series — do not take',1),
            ('title','Hannah Montana','Kids/Teen series — do not take',1),('title','High School Musical','Kids/Teen series — do not take',1),
            ('title','Olsen Twins','Kids/Teen series — do not take',1),('title','Precious Moments','Kids/Teen series — do not take',1),
            ('title','Sabrina the Teenage Witch','Kids/Teen series — do not take',1),
            ('title',"That's So Raven",'Kids/Teen series — do not take',1),
            ('title','Thomas the Train','Kids/Teen series — do not take',1),
            ('title','The Suite Life of Zack and Cody','Kids/Teen series — do not take',1),
            ('title','Everworld','Kids/Teen series by K.A. Applegate',1),
            ('title','Privilege Series','Kids/Teen series by Kate Brian',1),
            ('title','Three Cups of Tea','By Mortenson, Greg',1),('title','Stones for Schools','By Mortenson, Greg',1),
            ('title','America the Book','By Jon Stewart',1),('title','Free Military Wife Set/Devoted books','',1),
            ('title','The Fleet series','By Drake, David',1),
            ('author','Abbey, Lynn','',1),('author','Abbot, Jeff','',1),('author','Acevedo, Mario','',1),
            ('author','Acosta, Marta','',1),('author','Adair, Cherry','',1),('author','Adams, Cat','',1),
            ('author','Adams, C.T. & Clamp, Cathy','',1),('author','Adams, Will','',1),
            ('author','Adler, Elizabeth','',1),('author','Alan, Theresa','',1),
            ('author','Alexander, Hannah','',1),('author','Alexander, Victoria','',1),
            ('author','Allred, Katherine','',1),('author','Amory, Cleveland','',1),
            ('author','Andersen, B. Kent','',1),('author','Andersen, Susan','',1),
            ('author','Anderson, Catherine','',1),('author','Anderson, Jessica','',1),
            ('author','Andre, Bella','',1),('author','Andrews, Mary Kay','',1),
            ('author','Andrews, V.C.','Keep All Flowers in the Attic; Keep 1 OS HB MMPB',0),
            ('author','Archer, Alex','',1),('author','Archer, Jeffrey','Keep 1 MMPB/OS/HB',0),
            ('author','Armintrout, Jennifer','Take only 2015 and newer',0),
            ('author','Armstrong, Lori','',1),('author','Arthur, Keri','',1),
            ('author','Ashe, Katherine','',1),('author','Ashley, Amanda','',1),
            ('author','Ashworth, Adele','',1),('author','Auel, Jean','Keep All',0),
            ('author','Bacus, Kathleen','',1),('author','Bagshawe, Louise','NO OS/HB',0),
            ('author','Bagshawe, Tilly','NO OS/HB',0),('author','Baker, Jeanette','',1),
            ('author','Baldacci, David','Keep 1 OS 1 HB 2 MMPB',0),('author','Bangs, Nina','',1),
            ('author','Banks, L.A.','2018 and newer only',0),('author','Banks, Maya','',1),
            ('author','Bardsley, Michele','',1),('author','Barnes, Stephen','',1),
            ('author','Barton, Beverly','',1),('author','Basso, Adrienne','',1),
            ('author','Bear, Greg','Keep All',0),('author','Becker, James','',1),
            ('author','Bells, Heidi','',1),('author','Benedict, Alexandra','',1),
            ('author','Benford, Gregory','Keep All',0),('author','Berenson, Laurie','',1),
            ('author','Bernhardt, William','',1),('author','Berry, Steve','Keep All',0),
            ('author','Beverly, Jo','',1),('author','Binch, Maeve','Only 1 HB/OS; Only 1 MMPB',0),
            ('author','Birmingham, John','',1),('author','Blackstock, Terri','',1),
            ('author','Blake, Jennifer','',1),('author','Blanchard, Alice','',1),
            ('author','Block, Paul','',1),('author','Blue, Lucy','',1),
            ('author','Blume, Judy','No Adult Books',0),('author','Bond, Stephanie','',1),
            ('author','Bourne, Sam','',1),('author','Bova, Ben','Keep All',0),
            ('author','Boyle, Elizabeth','',1),('author','Brashares, Anne','NO OS/HB',0),
            ('author','Bradford, Barbara Taylor','',1),
            ('author','Bradley, James','Keep 3 Total — Flags of Our Fathers',0),
            ('author','Braunbeck, Gary A.','',1),('author','Brockman, Suzanne','',1),
            ('author','Brokaw, Charles','',1),('author','Brokaw, Tom','',1),
            ('author','Brooks, Terry','Keep All',0),('author','Brown, Dan','Keep 3 PB',0),
            ('author','Brown, Mary','',1),('author','Browne, Jill Conner','',1),
            ('author','Browne, Robert Gregory','',1),('author','Brunner, John','',1),
            ('author','Buff, Joe','',1),('author','Bush, George W.','',1),
            ('author','Bushnell, Candace','No HB/OS; Keep 2 PB',0),
            ('author','Byerrum, Ellen','',1),('author','Byrnes, Michael','',1),
            ('author','Cach, Lisa','',1),('author','Cahn, Jonathan','',1),
            ('author','Caldwell, Ian','',1),('author','Callen, Gayle','',1),
            ('author','Cameron, Stella','',1),('author','Canham, Marsha','',1),
            ('author','Cannell, Stephen','',1),('author','Carlyle, Liz','',1),
            ('author','Carrol, Ward','',1),('author','Carroll, Susan','',1),
            ('author','Carver, Jeffery','',1),('author','Castle, Jayne','',1),
            ('author','Chaikin, Linda','',1),('author','Chalker, Jack','',1),
            ('author','Chance, Karen','',1),('author','Chapman, Janet','',1),
            ('author','Chase, Loretta','',1),('author','Child, Lee','Keep 3',0),
            ('author','Christopher, Paul','',1),
            ('author','Clancy, Tom','Keep 1 OS 1 HB 2 MMPB; No OS Nonfiction',0),
            ('author','Clark, Mary Higgins','',1),('author','Clark, Simon','',1),
            ('author','Coffman, Elaine','',1),('author','Collins, Jackie','',1),
            ('author','Collins, Kate','',1),('author','Compton, Ralph','Keep All',0),
            ('author','Conroy, Pat','',1),('author','Cook, Robin','',1),
            ('author','Coontz, Stephen','No OS/HB',0),('author','Cosby, Bill','',1),
            ('author','Coyle, Harold','',1),('author','Crichton, Michael','Keep All',0),
            ('author','Dragon Lance','Keep 2 MMPB',0),('author','Drake, David','Keep All',0),
            ('author','Drake, Shannon','',1),('author','Duck Dynasty','',1),
            ('author','Duggar Family','',1),('author','Dugoni, Robert','',1),
            ('author','Duran, Meredith','',1),('author','Eddings, David','Keep All',0),
            ('author','Edwards, Cassie','',1),('author','Emerson, Earl','',1),
            ('author','Enger, Leif','',1),('author','Enoch, Suzanne','',1),
            ('author','Erdrich, Louise','',1),('author','Evans, Nicholas','',1),
            ('author','Evans, Richard Paul','',1),('author','Fairstein, Linda','',1),
            ('author','Feather, Jane','',1),('author','Ferrigno, Robert','',1),
            ('author','Fielding, Joy','',1),('author','Fielding, Helen','',1),
            ('author','Flag, Fannie','',1),('author','Fletcher, Donna','',1),
            ('author','Folsom, Allan','',1),('author','Forgotten Realms','Keep 2 MMPB',0),
            ('author','Frank, Dorothea Benton','',1),('author','Frank, Jacquelyn','',1),
            ('author','Freedman, J.F.','',1),('author','Freeman, Brian','',1),
            ('author','Freethey, Barbara','',1),('author','Frey, Stephen','',1),
            ('author','Frost, Jeaniene','',1),('author','Gabaldon, Diana','Keep All',0),
            ('author','Gaffney, Patricia','',1),('author','Galen, Shana','',1),
            ('author','Gandt, Robert','',1),('author','Gardner, James Alan','',1),
            ('author','Garey, Terri','',1),('author','Garlock, Dorothy','',1),
            ('author','Gemmell, David','Keep All',0),('author','Gibbons, Kaye','',1),
            ('author','Gibson, Rachel','',1),('author','Golden, Christopher','',1),
            ('author','Goldman, Joel','',1),('author','Goldsmith, Olivia','',1),
            ('author','Golemon, David','Keep All',0),('author','Goodkind, Terry','Keep All',0),
            ('author','Goodman, Jo','',1),('author','Goudge, Eileen','',1),
            ('author','Gould, Judith','',1),('author','Grace, Tom','',1),
            ('author','Graham, Heather','',1),('author','Grafton, Sue','',1),
            ('author','Grant, Andrew','',1),('author','Greanis, Thomas','',1),
            ('author','Greeley, Andrew','',1),('author','Green, Jane','',1),
            ('author','Green, Simon R.','Keep All',0),('author','Green, Tim','',1),
            ('author','Greiman, Lois','',1),('author','Griffin, Laura','',1),
            ('author','Guhrke, Laura Lee','',1),('author','Haig, Brian','',1),
            ('author','Hamid, Mohsin','',1),('author','Hamilton, Steve','',1),
            ('author','Handeland, Lori','',1),('author','Handler, Chelsea','',1),
            ('author','Hannah, Kristin','Keep All',0),
            ('author','Harris, Charlaine','Keep 1 OS/HB Sookie Stackhouse',0),
            ('author','Harris, Joshua','',1),('author','Harrison, Kim','',1),
            ('author','Hart, Catherine','',1),('author','Hart, Erin','',1),
            ('author','Hart, John','',1),('author','Hartley, A.J.','',1),
            ('author','Hartzmark, Donald','',1),('author','Havens, Candace','NO OS/HB',0),
            ('author','Hawkins, Alexandra','',1),('author','Haynes, Dana','',1),
            ('author','Heath, Lorraine','',1),('author','Heggan, Christine','',1),
            ('author','Heitman, Lynne','',1),('author','Henke, Shirl','',1),
            ('author','Hess, Maya','',1),('author','Holly, Emma','',1),
            ('author','Holm, Steph-Ann','',1),('author','Holt, Cheryl','',1),
            ('author','Howard, Linda','',1),('author','Howell, Hannah','',1),
            ('author','Hoyt, Elizabeth','',1),('author','Hunter, Jillian','',1),
            ('author','Hurley, Graham','',1),('author','Hunter, Madeline','',1),
            ('author','Hunter, Stephen','',1),('author','Inclan, Jessica Barksdale','',1),
            ('author','Ing, Dean','',1),('author','Isaacs, Susan','',1),
            ('author','Jackson, Lisa','No historical romance',0),
            ('author','James, Eloisa','',1),('author','James, Samantha','',1),
            ('author','Jefferies, Sabrina','',1),
            ('author','Johansen, Iris','No Romance/Historical Romance',0),
            ('author','Johnson, Joan','',1),('author','Johnson, Susan','',1),
            ('author','Johnstone, William W.','Keep 1 MMPB',0),
            ('author','Jones, Darynda','',1),('author','Jones, Edward P.','',1),
            ('author','Jones, Linda Winstead','',1),('author','Jordan, Nicole','',1),
            ('author','Jordan, Robert','Keep All',0),
            ('author','Jordan, Sophie','',1),('author','Joyce, Brenda','',1),
            ('author','Kane, Andrea','',1),('author','Kane, Kathleen','',1),
            ('author','Karon, Jan','',1),('author','Katra, Virginia','',1),
            ('author','Kearney, Susan','',1),('author','Keating, Taylor','',1),
            ('author','Kellerman, Faye','',1),
            ('author','Kellerman, Faye & Peter Decker','Only Lazarus series & standalones 2015 and newer',0),
            ('author','Kellerman, Jonathan','Keep 1 OS/HB',0),
            ('author','Kennedy, Kathryne','',1),('author','Keyes, Marian','',1),
            ('author','Kinsella, Sophie','No Shopaholic Series; Only take 2010 and newer',0),
            ('author','Kiyosaki, Robert T.','Keep all finance',0),
            ('author','Kleypas, Lisa','Take 2018 and newer',0),
            ('author','Knight, Angela','',1),('author','Kohler, Sharie','',1),
            ('author','Koomson, Dorothy','NO OS/HB',0),
            ('author','Koontz, Dean',"Keep All 'Odd' series",0),
            ('author','Krentz, Jayne Ann','',1),('author','Krinard, Susan','',1),
            ('author','Kurland, Lynn','',1),('author','Lahaye, Tim','',1),
            ('author','Lahaye, Tim and Jerry B Jenkins','Keep 1',0),
            ('author','Land, Jon','',1),('author','Lashner, William','',1),
            ('author','Larson, Elyse','',1),('author','Laurens, Stephanie','',1),
            ('author','Laymon, Richard','',1),('author','Leather, Stephen','',1),
            ('author','Leigh, Steven','',1),('author','Leon, Donna','',1),
            ('author','Letts, Billie','',1),('author','Levine, Paul','',1),
            ('author','Lewis, Beverly','',1),('author','Lindsay, Johanna','',1),
            ('author','Lindsey, David','',1),('author','Lin, Majorie M.','',1),
            ('author','Litton, Josie','',1),('author','Logan, Chuck','',1),
            ('author','Loomis, Greg','',1),('author','Long, Julie Ann','',1),
            ('author','Lowell, Elizabeth','',1),('author','Ludlum, Robert','Keep 1 OS 1 HB',0),
            ('author','Lumley, Brian','Keep All',0),('author','Macalister, Katie','',1),
            ('author','Macallan, Ben','',1),('author','Macdonald, John','',1),
            ('author','Mackay, Scott','',1),('author','Mackenzie, Sarah','',1),
            ('author','Mailer, Norman','',1),('author','Maguire, Margo','',1),
            ('author','Major, Ann','',1),('author','Mallery, Susan','',1),
            ('author','Mallory, Anne','',1),('author','Mallory, Margaret','',1),
            ('author','Maloney, Jack','',1),('author','Mansell, Jill','',1),
            ('author','March, Emily','',1),('author','Marcinko, Richard','',1),
            ('author','Margocis, Sue','',1),('author','Margolin, Phillip','',1),
            ('author','Markham, Lisa','',1),('author','Marsh, Ngaio','',1),
            ('author','Martin, George R.R.','Keep All',0),('author','Martin, Kat','',1),
            ('author','Mason, Connie','',1),('author','Matthews, Carol','',1),
            ('author','Max, Tucker','',1),('author','Maxted, Anna','',1),
            ('author','Maxwell, Cathy','',1),('author','Mayhue, Melissa','',1),
            ('author','McCaffrey, Anne','Keep All',0),('author','McCall, Dinah','',1),
            ('author','McCall, Penny','',1),('author','McCarthy, Erin','',1),
            ('author','McCarthy, Jenny','',1),('author','McCoy, Judi','',1),
            ('author','McCray, Cheyenne','',1),('author','McEwan, Ian','Keep All',0),
            ('author','McGarrity, Michael','',1),('author','McKenna, Lindsay','',1),
            ('author','McLaughlin, Emma','',1),('author','Medeiros, Theresa','',1),
            ('author','Michaels, Barbara','',1),('author','Michaels, Fern','',1),
            ('author','Michaels, Kasey','',1),('author','Milan, Courtney','',1),
            ('author','Miller, John Ramsey','',1),('author','Mitchard, Jaquelyn','',1),
            ('author','Mobley, C.A.','',1),('author','Mofina, Rick','',1),
            ('author','Momaday, N. Scott','',1),('author','Moning, Karen Marie','',1),
            ('author','Monroe, Mary','',1),('author','Moore, Margaret','',1),
            ('author','Moore, Michael','',1),('author','Morgan, Alexis','',1),
            ('author','Morris, Gilbert','',1),
            ('author','Mortenson, Greg','Do not take Three Cups of Tea or Stones for Schools',0),
            ('author','Mosely, Walter','',1),('author','Murphy, Warren','',1),
            ('author','Napier, Bill','',1),('author','Naylor, Clare','',1),
            ('author','Neggers, Carla','',1),('author','Noble, Elizabeth','',1),
            ('author','North, Oliver','',1),('author','Nostradamus','',1),
            ('author','Novak, Brenda','',1),("author","O'Banyon, Constance","",1),
            ("author","O'Brien, Kevin","",1),("author","O'Brien, Meg","",1),
            ("author","O'Flanigan, Sheila","",1),
            ("author","O'Reilly, Bill","Only take the 'Killing' series",0),
            ("author","O'Shaunessey, Lawrence","",1),("author","O'Shanuessey, Perry","",1),
            ('author','Oke, Janette','',1),('author','Pace, Brenda','',1),
            ('author','Palin, Sarah','',1),('author','Palmer, Diana','',1),
            ('author','Palmer, Michael','Only 2012 and newer',0),
            ('author','Palou, Stel','',1),('author','Pampered Chef','',1),
            ('author','Parker, Barbara','',1),('author','Parker, T. Jefferson','',1),
            ('author','Parrish, P.J.','',1),
            ('author','Patterson, James','Keep 1 OS 1 HB 2 MMPB',0),
            ('author','Paul, Graham Sharp','',1),('author','Pearl, Michael or Debi','',1),
            ('author','Pears, Iain','',1),('author','Pearson, Ridley','',1),
            ('author','Pella, Judith','',1),('author','Perdue, Lewis','',1),
            ('author','Perry, Ann','',1),('author','Perry, Thomas','',1),
            ('author','Peters, Ralph','',1),('author','Petrucha, Stefan','',1),
            ('author','Phillips, Bill','',1),('author','Phillips, Susan Elizabeth','',1),
            ('author','Plain, Belva','',1),('author','Plumley, Lisa','',1),
            ('author','Pohl, Fredrick','',1),('author','Poyer, David','',1),
            ('author','Putney, Mary Jo','',1),('author','Pratt, James Michael','',1),
            ('author','Pratt, Scott','',1),('author','Quick, Amanda','',1),
            ('author','Quindlen, Anna','',1),
            ('author','Quinn, Julia','Take 2018 and newer; Take all Bridgerton',0),
            ('author','Raleigh, Deborah','',1),('author','Ranny, Karen','',1),
            ('author','Raye, Jennifer','',1),('author','Reed, Rick','',1),
            ('author','Reeves-Stevens, Judith & Garfield','',1),
            ('author','Reich, Christopher','',1),('author','Reiss, Bob','',1),
            ('author','Reynolds, Sheri','',1),('author','Richards, Emilie','NO OS/HB',0),
            ('author','Rice, Anne','Keep All',0),
            ('author','Rice, Luanne','Only take 2012 and newer',0),
            ('author','Rice, Patricia','',1),('author','Ridgeway, Christie','',1),
            ('author','Riker, Jay','',1),('author','Robards, Karen','',1),
            ('author','Robb, J.D.','Keep 1',0),('author','Robbins, Harold','',1),
            ('author','Roberts, Nora','Keep 1',0),('author','Robinson, Patrick','',1),
            ('author','Rogers, Rosemary','',1),('author','Rollins, David','',1),
            ('author','Ross, Joann','',1),('author','Russe, Savannah','',1),
            ('author','Ryan, Charles','',1),('author','Sala, Sharon','',1),
            ('author','Sanders, Lawrence','',1),
            ('author','Sanford, John','Keep 1 OS HB 2 MMPB',0),
            ('author','Sands, Lynsay','',1),('author','Savage, Tom','',1),
            ('author','Sawyer, Meryl','',1),('author','Sawyer, Robert J.','',1),
            ('author','Scott, Amanda','',1),
            ('author','Scottoline, Lisa','Only take books 2010 and newer',0),
            ('author','Seymour, Gerald','',1),('author','Shay, Kathryn','',1),
            ('author','Sheldon, Sidney','',1),('author','Shreve, Anita','',1),
            ('author','Siddons, Anne Rivers','',1),('author','Simonson, Helen','',1),
            ('author','Singh, Nalini','',1),('author','Sittenfeld, Curtis','',1),
            ('author','Sizemore, Susan','',1),('author','Sloane, Stefanie','',1),
            ('author','Small, Beatrice','',1),('author','Smiley, Jane','',1),
            ('author','Smith, Alexander McCall','No No. 1 Ladies Detective Agency Series',0),
            ('author','Smith, Bobbi','',1),('author','Smith, Debra White','',1),
            ('author','Snelling, Lauraine','',1),('author','Snooki','',1),
            ('author','Sparks, Kerrelyn','',1),('author','Spear, Terry','',1),
            ('author','Spelling, Tori','',1),('author','Spindler, Erica','',1),
            ('author','Squires, Susan','',1),('author','St. Claire, Roxanne','',1),
            ('author','Starling, Boris','',1),('author','Stasheff, Christopher','',1),
            ('author','Steel, Danielle','Keep 1',0),
            ('author','Stenzel, Natali','',1),('author','Stein, Jeanne C.','',1),
            ('author','Stewart, Jon','Do not take America the Book',0),
            ('author','Stewart, Mariah','',1),
            ('author','Stockett, Kathryn','Keep All',0),
            ('author','Stone, David','',1),('author','Stone, Robert','',1),
            ('author','Strieber, Whitley','',1),('author','Strout, Anton','',1),
            ('author','Strout, Elizabeth','Keep 2',0),('author','Storm, P.W.','',1),
            ('author','Stroud, Carsten','',1),('author','Stuart, Anne','',1),
            ('author','Sutcliffe, Katherine','',1),('author','Sundaresan, Indu','',1),
            ('author','Swain, James','',1),('author','Sykes, Plum','NO OS/HB',0),
            ('author','Tananbaum, Robert K.','',1),('author','Thomas, Craig','',1),
            ('author','Thomas, Jodi','',1),('author','Thompson, Colleen','',1),
            ('author','Thompson, Ronda','',1),('author','Tracy, P.J.','',1),
            ('author','Trigiani, Adriana','',1),('author','Trollope, Joanna','',1),
            ('author','Truscott, Lucian','',1),('author','Turow, Scott','',1),
            ('author','Tyler, Anne','',1),('author','Unger, Lisa','',1),
            ('author','Uris, Leon','',1),('author','Verdon, John','',1),
            ('author','Viehl, Lynn','',1),('author','Vincenzi, Penny','',1),
            ('author','Vine, Barbara','',1),('author','Walker, Robert W.','',1),
            ('author','Waller, Robert James','',1),('author','Walters, Minette','',1),
            ('author','Wambaugh, Joseph','',1),('author','Ward, J.R.','NO OS/HB',0),
            ('author','Warren, Christine','',1),('author','Warren, Tracey','',1),
            ('author','Weisberger, Lauren','',1),('author','Welfonder, Sue-Ellen','',1),
            ('author','Wells, Rebecca','',1),('author','Westlake, Donald E.','',1),
            ('author','White, Cecil Ward','',1),('author','White, Steve','',1),
            ('author','Wick, Lori','',1),('author','Wickham, Madeleine','',1),
            ('author','Wiel, Lisa','',1),
            ('author','Wiener, Jennifer','Take 2018 and newer',0),
            ('author','Wiesberger, Jill','',1),('author','Wiesman, John','',1),
            ('author','Wiggs, Susan','',1),('author','Wilde, Lori','',1),
            ('author','Woods, Sherryl','',1),('author','Woods, Stuart','No HB/OS',0),
            ('author','Woodwiss, Kathleen','',1),('author','York, Rebecca','',1),
            ('author','Applegate, K.A.','Do not take Everworld',0),
            ('author','Avi','',1),
            ('author','Brian, Kate','Do not take Privilege Series',0),
            ('author','Brashares, Ann','Do not take Sisterhood of the Traveling Pants',0),
            ('author','Byars, Betsy','',1),
            ('author','Cabot, Meg','Do not take The Mediator Series',0),
            ('author','Caine, Rachel','',1),
            ('author','Calonita, Jen','Do not take Secrets of My Hollywood Life',0),
            ('author','De La Cruz, Melissa','Only 2010 or newer; Do not take Blue Blood',0),
            ('author','Dean, Zoey','',1),
            ('author','Ewing, Lynna','Do not take Daughter of the Moon',0),
            ('author','Gilmour, H.B.','Do not take Twitches',0),
            ('author','Hale, Shannon','Do not take Ever After High',0),
            ('author','Harrison, Lisi','Do not take The Clique Series or Monster High',0),
            ('author','Krulik, Nancy E.','Do not take Katie Kazoo',0),
            ('author','Lisle, Janet Taylor','',1),
            ('author','Meyer, Stephenie','Keep only 3 Twilight; 2 for all others',0),
            ('author','Morgan, Melissa J.','Do not take Camp Confidential',0),
            ('author','Nimmo, Jenny','Do not take Children of the Red King (Charlie Bone)',0),
            ('author','Pascal, Francine','Do not take Sweet Valley High',0),
            ('author','Peck, Richard','',1),
            ('author','Rodda, Emily','Do not take Deltora Quest',0),
            ('author','Rylant, Cynthia','',1),
            ('author','Shepard, Sara','Do not take Pretty Little Liars',0),
            ('author','Smith, L.J.','',1),('author','Snyder, Zilpha Keatley','',1),
            ('author','Stone, Jeff','',1),('author','Van Draanen, Wendelin','',1),
            ('author','Von Ziegesar, Cecily','Do not take Gossip Girl or It Girl Series',0),
            ('author','Wasserman, Robin','Do not take Seven Deadly Sins',0),
            ('author','Wilson, Jacqueline','',1),
        ]
        c.executemany(
            "INSERT OR IGNORE INTO do_not_take (type,value,note,do_not_take) VALUES (?,?,?,?)",
            _DNT_SEED)

    # Seed genre list if empty
    _GENRE_SEED = sorted([
        "Adventure/Survival", "American History", "Art/Art History", "Biography",
        "Book Club", "Classic", "Collectibles", "Comic Book", "Cookbook",
        "Crafts/Gardening", "Education/Dictionaries", "Fantasy", "Financial",
        "General Fiction", "Graphic Novel", "Historical Fiction", "History",
        "Horror", "Kids", "Manga", "Mystery", "New Age/Paranormal", "Pets/Animals",
        "Religion/Religious Fiction", "Romance", "Sci-Fi", "Self Help", "Specialty",
        "Sports", "Travel", "TV/Movie/Entertainment", "War/Military",
        "World History", "Young Adult",
    ])
    for _g in _GENRE_SEED:
        c.execute("INSERT OR IGNORE INTO genres (name) VALUES (?)", (_g,))

    try:
        c.execute("ALTER TABLE inventory ADD COLUMN price REAL")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE inventory ADD COLUMN location TEXT")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE customers ADD COLUMN collectible_credit REAL DEFAULT 0.0")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE credit_log ADD COLUMN credit_type TEXT DEFAULT 'regular'")
    except Exception:
        pass

    c.execute("SELECT COUNT(*) FROM daily_discounts")
    if c.fetchone()[0] == 0:
        daily_seed = [
            (0, "Mystery Monday",         "Mystery",                25),
            (1, "Tasty Tuesday",          "Cookbooks",              25),
            (2, "Wars Wednesday",         "War/Military",           25),
            (3, "Timeless Thursday",      "Classics",               15),
            (4, "Fabled Treasure Friday", "Collectibles/Specialty", 10),
            (4, "Fabled Treasure Friday", "Kids/YA",                50),
            (5, "Small Readers Saturday", "Kids/YA",                50),
        ]
        c.executemany(
            "INSERT INTO daily_discounts (day_num,day_name,genre,pct) VALUES (?,?,?,?)",
            daily_seed)

    c.execute("SELECT COUNT(*) FROM monthly_discounts")
    if c.fetchone()[0] == 0:
        monthly_seed = [
            (1,"Book Club"),(1,"Self Help"),(1,"Biographies"),(1,"SCI-FI"),
            (2,"Romance"),(2,"History"),(2,"Historical Fiction"),(2,"Culture"),
            (3,"Graphic Novels"),(3,"Comics"),(3,"Manga"),(3,"Cookbooks"),
            (3,"Pets and Animals"),(3,"Dictionaries/Education"),
            (4,"Poetry/Literature"),(4,"Humor"),(4,"Religion/Religious Fiction"),(4,"Fantasy"),
            (5,"Crafts & Gardening"),(5,"Mystery"),(5,"Wars & Military"),(5,"SCI-FI"),
            (6,"General Fiction"),(6,"Travel Guides"),(6,"Cookbooks"),
            (6,"Adventure and Survival"),(6,"Self Help"),
            (7,"American History"),(7,"Book Club"),(7,"Award Winners"),
            (7,"Sports"),(7,"Historical Fiction"),
            (8,"Biographies"),(8,"Comics"),(8,"Graphic Novels"),(8,"Manga"),
            (8,"Romance"),(8,"TV"),(8,"Movies"),(8,"Entertainment"),
            (9,"Book Club"),(9,"Science"),(9,"Biographies"),(9,"Art"),(9,"Art History"),
            (10,"Horror"),(10,"New Age/Paranormal"),(10,"Music"),
            (11,"Cookbooks"),(11,"Dictionaries/Education"),
            (11,"Wars & Military"),(11,"General Fiction"),
            (12,"Crafts/Hobbies"),(12,"Cookbooks"),(12,"Mystery"),
            (12,"Religion/Religious Fiction"),
        ]
        c.executemany(
            "INSERT INTO monthly_discounts (month_num,genre,pct) VALUES (?,?,25)",
            monthly_seed)
        c.execute(
            "INSERT INTO monthly_discounts (month_num,genre,pct) VALUES (12,?,15)",
            ("Collectibles & Specialty",))

    conn.commit()
    conn.close()


# ── Genre DB helpers ─────────────────────────────────────────────────────────
def get_all_genres():
    """Return sorted list of genre name strings from DB."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM genres ORDER BY name")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]


def ensure_genre(name):
    """Add genre to DB if it doesn't already exist."""
    name = name.strip()
    if not name:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO genres (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()


def rename_genre(old_name, new_name):
    """Rename a genre everywhere it appears."""
    new_name = new_name.strip()
    if not new_name or old_name == new_name:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE genres SET name=? WHERE name=?", (new_name, old_name))
    c.execute("UPDATE inventory SET genre=? WHERE genre=?", (new_name, old_name))
    c.execute("UPDATE daily_discounts SET genre=? WHERE genre=?", (new_name, old_name))
    c.execute("UPDATE monthly_discounts SET genre=? WHERE genre=?", (new_name, old_name))
    c.execute("UPDATE special_sales SET genre=? WHERE genre=?", (new_name, old_name))
    c.execute("UPDATE sale_items SET genre=? WHERE genre=?", (new_name, old_name))
    conn.commit()
    conn.close()


def delete_genre(name):
    """Remove genre from master list (does not touch existing data)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM genres WHERE name=?", (name,))
    conn.commit()
    conn.close()


# ── Settings helpers ──────────────────────────────────────────────────────────
def get_setting(key):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def set_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, value))
    conn.commit()
    conn.close()


# ── Inventory helpers ─────────────────────────────────────────────────────────
def get_next_invoice():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='last_invoice'")
    last = int(c.fetchone()[0])
    next_inv = last + 1
    c.execute("UPDATE settings SET value=? WHERE key='last_invoice'", (next_inv,))
    conn.commit()
    conn.close()
    return next_inv


def revert_invoice():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='last_invoice'")
    last = int(c.fetchone()[0])
    if last > 0:
        c.execute("UPDATE settings SET value=? WHERE key='last_invoice'", (last - 1,))
    conn.commit()
    conn.close()


def get_book_by_invoice(invoice_no):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT id,invoice_no,isbn,title,author,genre,price,location
                 FROM inventory WHERE invoice_no=?""", (invoice_no,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "invoice_no": row[1], "isbn": row[2], "title": row[3],
            "author": row[4], "genre": row[5], "price": row[6], "location": row[7]}


def get_all_books(search="", field="All"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    base = "SELECT invoice_no,title,author,genre,price,location,isbn,id FROM inventory"
    if search:
        s = f"%{search}%"
        if field == "Title":
            c.execute(f"{base} WHERE title LIKE ? ORDER BY invoice_no DESC", (s,))
        elif field == "Author":
            c.execute(f"{base} WHERE author LIKE ? ORDER BY invoice_no DESC", (s,))
        elif field == "ISBN":
            c.execute(f"{base} WHERE isbn LIKE ? ORDER BY invoice_no DESC", (s,))
        elif field == "Genre":
            c.execute(f"{base} WHERE genre LIKE ? ORDER BY invoice_no DESC", (s,))
        else:
            c.execute(f"{base} WHERE title LIKE ? OR author LIKE ? OR isbn LIKE ? OR genre LIKE ? ORDER BY invoice_no DESC", (s, s, s, s))
    else:
        c.execute(f"{base} ORDER BY invoice_no DESC")
    rows = c.fetchall()
    conn.close()
    return rows


def save_book(invoice_no, isbn, title, author, genre, price, location):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO inventory (invoice_no,isbn,title,author,genre,price,location)
                 VALUES (?,?,?,?,?,?,?)""",
              (invoice_no, isbn, title, author, genre, price, location))
    conn.commit()
    conn.close()


def update_book(book_id, isbn, title, author, genre, price, location):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""UPDATE inventory SET isbn=?,title=?,author=?,genre=?,price=?,location=?
                 WHERE id=?""",
              (isbn, title, author, genre, price, location, book_id))
    conn.commit()
    conn.close()


def delete_book(book_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM inventory WHERE id=?", (book_id,))
    conn.commit()
    conn.close()


def reduce_inventory(invoice_no):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM inventory WHERE invoice_no=?", (invoice_no,))
    conn.commit()
    conn.close()


# ── Customer helpers ──────────────────────────────────────────────────────────
def get_all_customers(search=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if search:
        s = f"%{search}%"
        c.execute("""SELECT id,name,phone,email,deros_date,preferred_contact,
                     social_handle,store_credit,collectible_credit
                     FROM customers WHERE name LIKE ? OR phone LIKE ? OR email LIKE ? OR social_handle LIKE ?
                     ORDER BY name""", (s, s, s, s))
    else:
        c.execute("""SELECT id,name,phone,email,deros_date,preferred_contact,
                     social_handle,store_credit,collectible_credit
                     FROM customers ORDER BY name""")
    rows = c.fetchall()
    conn.close()
    return rows


def get_customer(customer_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT id,name,phone,email,deros_date,preferred_contact,
                 social_handle,store_credit,collectible_credit
                 FROM customers WHERE id=?""", (customer_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "name": row[1], "phone": row[2], "email": row[3],
            "deros_date": row[4], "preferred_contact": row[5],
            "social_handle": row[6], "store_credit": row[7],
            "collectible_credit": row[8]}


def save_customer(name, phone, email, deros_date, preferred_contact, social_handle):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO customers
                 (name,phone,email,deros_date,preferred_contact,social_handle,
                  store_credit,collectible_credit)
                 VALUES (?,?,?,?,?,?,0.0,0.0)""",
              (name, phone, email, deros_date, preferred_contact, social_handle))
    conn.commit()
    conn.close()


def update_customer(customer_id, name, phone, email, deros_date,
                    preferred_contact, social_handle):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""UPDATE customers SET name=?,phone=?,email=?,deros_date=?,
                 preferred_contact=?,social_handle=? WHERE id=?""",
              (name, phone, email, deros_date, preferred_contact,
               social_handle, customer_id))
    conn.commit()
    conn.close()


def delete_customer(customer_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM customers WHERE id=?", (customer_id,))
    c.execute("DELETE FROM credit_log WHERE customer_id=?", (customer_id,))
    c.execute("DELETE FROM wants WHERE customer_id=?", (customer_id,))
    conn.commit()
    conn.close()


# ── Wants helpers ─────────────────────────────────────────────────────────────
def add_want(customer_id, title, author, isbn, notes):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO wants (customer_id, title, author, isbn, notes)
                 VALUES (?,?,?,?,?)""",
              (customer_id, title or None, author or None, isbn or None, notes or None))
    conn.commit()
    conn.close()


def get_wants_for_customer(customer_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT id, title, author, isbn, notes, date_added
                 FROM wants WHERE customer_id=? AND fulfilled=0
                 ORDER BY date_added DESC""", (customer_id,))
    rows = c.fetchall()
    conn.close()
    return rows


def delete_want(want_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM wants WHERE id=?", (want_id,))
    conn.commit()
    conn.close()


def check_wants(title, author, isbn):
    """Return list of (customer_name, want_id, title, author, isbn, notes, date_added)
    for any unfulfilled want that fuzzy-matches the given book."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    conditions = []
    params = []
    if title:
        conditions.append("(w.title IS NOT NULL AND w.title LIKE ?)")
        params.append(f"%{title}%")
    if author:
        conditions.append("(w.author IS NOT NULL AND w.author LIKE ?)")
        params.append(f"%{author}%")
    if isbn:
        conditions.append("(w.isbn IS NOT NULL AND w.isbn=?)")
        params.append(isbn)
    if not conditions:
        conn.close()
        return []
    where = " OR ".join(conditions)
    c.execute(f"""SELECT cu.name, w.id, w.title, w.author, w.isbn, w.notes, w.date_added
                  FROM wants w JOIN customers cu ON cu.id=w.customer_id
                  WHERE w.fulfilled=0 AND ({where})
                  ORDER BY cu.name""", params)
    rows = c.fetchall()
    conn.close()
    return rows


def mark_want_fulfilled(want_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE wants SET fulfilled=1 WHERE id=?", (want_id,))
    conn.commit()
    conn.close()


def add_credit_transaction(customer_id, amount, note, credit_type="regular"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("""INSERT INTO credit_log (customer_id,date,amount,credit_type,note)
                 VALUES (?,?,?,?,?)""",
              (customer_id, date_str, amount, credit_type, note))
    if credit_type == "collectible":
        c.execute("UPDATE customers SET collectible_credit = collectible_credit + ? WHERE id=?",
                  (amount, customer_id))
    else:
        c.execute("UPDATE customers SET store_credit = store_credit + ? WHERE id=?",
                  (amount, customer_id))
    conn.commit()
    conn.close()


def get_credit_log(customer_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT date,amount,credit_type,note FROM credit_log
                 WHERE customer_id=? ORDER BY id DESC""", (customer_id,))
    rows = c.fetchall()
    conn.close()
    return rows


# ── Special Sales helpers ─────────────────────────────────────────────────────
def get_special_sales():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id,genre,pct,start_date,end_date,note FROM special_sales ORDER BY start_date")
    rows = c.fetchall()
    conn.close()
    return rows


def save_special_sale(genre, pct, start_date, end_date, note):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO special_sales (genre,pct,start_date,end_date,note) VALUES (?,?,?,?,?)",
              (genre, pct, start_date, end_date, note))
    conn.commit()
    conn.close()


def delete_special_sale(sale_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM special_sales WHERE id=?", (sale_id,))
    conn.commit()
    conn.close()


def get_active_special_sale(genre, today_str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT pct FROM special_sales
                 WHERE genre=? AND start_date <= ? AND end_date >= ?
                 ORDER BY pct DESC LIMIT 1""",
              (genre, today_str, today_str))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0.0


# ── Daily/Monthly Discount DB helpers ────────────────────────────────────────
def get_daily_discounts_for_day(day_num):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id,day_name,genre,pct FROM daily_discounts WHERE day_num=? ORDER BY id",
              (day_num,))
    rows = c.fetchall()
    conn.close()
    return rows


def get_monthly_discounts_for_month(month_num):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id,genre,pct FROM monthly_discounts WHERE month_num=? ORDER BY genre",
              (month_num,))
    rows = c.fetchall()
    conn.close()
    return rows


def add_daily_discount(day_num, day_name, genre, pct):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO daily_discounts (day_num,day_name,genre,pct) VALUES (?,?,?,?)",
              (day_num, day_name, genre, pct))
    conn.commit()
    conn.close()


def update_daily_discount_genre(discount_id, genre):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE daily_discounts SET genre=? WHERE id=?", (genre, discount_id))
    conn.commit()
    conn.close()


def delete_daily_discount(discount_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM daily_discounts WHERE id=?", (discount_id,))
    conn.commit()
    conn.close()


def add_monthly_discount(month_num, genre, pct):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO monthly_discounts (month_num,genre,pct) VALUES (?,?,?)",
              (month_num, genre, pct))
    conn.commit()
    conn.close()


def delete_monthly_discount(discount_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM monthly_discounts WHERE id=?", (discount_id,))
    conn.commit()
    conn.close()


# ── Do Not Take helpers ──────────────────────────────────────────────────────
def get_do_not_take(search="", filter_type="All"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    type_map = {"Author": "author", "Title": "title", "Category": "category"}
    type_filter = type_map.get(filter_type)
    base = "SELECT id,type,value,note,do_not_take FROM do_not_take"
    order = "ORDER BY type,value"
    if search:
        s = f"%{search}%"
        if type_filter:
            c.execute(f"{base} WHERE type=? AND value LIKE ? {order}", (type_filter, s))
        else:
            c.execute(f"{base} WHERE value LIKE ? {order}", (s,))
    else:
        if type_filter:
            c.execute(f"{base} WHERE type=? {order}", (type_filter,))
        else:
            c.execute(f"{base} {order}")
    rows = c.fetchall()
    conn.close()
    return rows


def check_do_not_take(title="", author=""):
    """Return list of matching DNT entries (partial match on title/author)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    matches = []
    if title:
        t = f"%{title.strip()}%"
        c.execute("SELECT id,type,value,note,do_not_take FROM do_not_take WHERE type='title' AND LOWER(value) LIKE LOWER(?)", (t,))
        matches += c.fetchall()
    if author:
        a = f"%{author.strip()}%"
        c.execute("SELECT id,type,value,note,do_not_take FROM do_not_take WHERE type='author' AND LOWER(value) LIKE LOWER(?)", (a,))
        matches += c.fetchall()
    conn.close()
    return matches


def save_do_not_take(entry_type, value, note, do_not_take=True):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO do_not_take (type,value,note,do_not_take) VALUES (?,?,?,?)",
              (entry_type, value.strip(), note.strip(), 1 if do_not_take else 0))
    conn.commit()
    conn.close()


def update_do_not_take(entry_id, entry_type, value, note, do_not_take=True):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE do_not_take SET type=?,value=?,note=?,do_not_take=? WHERE id=?",
              (entry_type, value.strip(), note.strip(), 1 if do_not_take else 0, entry_id))
    conn.commit()
    conn.close()


def delete_do_not_take(entry_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM do_not_take WHERE id=?", (entry_id,))
    conn.commit()
    conn.close()


# ── Sales helpers ─────────────────────────────────────────────────────────────
def save_sale(customer_id, items, subtotal, discount_total, total,
              payment_cash, payment_card, payment_credit):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("""INSERT INTO sales (date,customer_id,subtotal,discount_total,total,
                 payment_cash,payment_card,payment_credit)
                 VALUES (?,?,?,?,?,?,?,?)""",
              (date_str, customer_id, subtotal, discount_total, total,
               payment_cash, payment_card, payment_credit))
    sale_id = c.lastrowid
    for item in items:
        c.execute("""INSERT INTO sale_items
                     (sale_id,invoice_no,title,genre,orig_price,discount_pct,final_price)
                     VALUES (?,?,?,?,?,?,?)""",
                  (sale_id, item["invoice_no"], item["title"], item["genre"],
                   item["orig_price"], item["discount_pct"], item["final_price"]))
    conn.commit()
    conn.close()
    return sale_id


# ── Discount Engine ───────────────────────────────────────────────────────────
def get_discount_for_book(book):
    genre = (book.get("genre") or "").strip()
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    weekday = today.weekday()
    month = today.month
    is_collectible = any(g.lower() in genre.lower() for g in COLLECTIBLE_GENRES)

    daily_pct = 0.0
    daily_label = ""
    day_rules = get_daily_discounts_for_day(weekday)
    for did, day_name, rule_genre, pct in day_rules:
        if is_collectible and rule_genre.lower() not in \
                {g.lower() for g in COLLECTIBLE_GENRES}:
            continue
        if rule_genre.lower() == genre.lower() and pct > daily_pct:
            daily_pct = pct
            daily_label = f"{day_name} ({pct:.0f}% off)"

    monthly_pct = 0.0
    monthly_label = ""
    month_rules = get_monthly_discounts_for_month(month)
    for mid, disc_genre, pct in month_rules:
        if disc_genre.lower() == genre.lower() and pct > monthly_pct:
            monthly_pct = pct
            monthly_label = f"{MONTHS[month]} Sale ({pct:.0f}% off)"

    special_pct = get_active_special_sale(genre, today_str)
    special_label = f"Special Sale ({special_pct:.0f}% off)" if special_pct > 0 else ""

    best_pct = max(daily_pct, monthly_pct, special_pct)
    if best_pct == 0:
        return 0.0, ""
    if best_pct == daily_pct and daily_pct > 0:
        return daily_pct, daily_label
    if best_pct == monthly_pct and monthly_pct > 0:
        return monthly_pct, monthly_label
    return special_pct, special_label


def get_todays_banners():
    weekday = date.today().weekday()
    month = date.today().month
    day_rules = get_daily_discounts_for_day(weekday)
    if day_rules:
        day_name = day_rules[0][1]
        parts = ", ".join(f"{r[3]:.0f}% off {r[2]}" for r in day_rules)
        daily_text = f"Today: {day_name} — {parts}"
    else:
        daily_text = "No daily discount today"
    month_rules = get_monthly_discounts_for_month(month)
    if month_rules:
        parts = ", ".join(f"{r[1]} {r[2]:.0f}% off" for r in month_rules)
        monthly_text = f"{MONTHS[month]}: {parts}"
    else:
        monthly_text = ""
    return daily_text, monthly_text


# ── Name helpers ──────────────────────────────────────────────────────────────
def to_last_first(name):
    """Convert 'First [Middle] Last' → 'Last, First [Middle]'. No-op if already contains a comma."""
    name = name.strip()
    if not name or "," in name:
        return name
    parts = name.split()
    if len(parts) == 1:
        return name
    return f"{parts[-1]}, {' '.join(parts[:-1])}"


def validate_last_first(name):
    """Return True if name is 'Last, First' with both parts non-empty."""
    if "," not in name:
        return False
    last, first = name.split(",", 1)
    return bool(last.strip()) and bool(first.strip())


# ── Google Books API ──────────────────────────────────────────────────────────
def lookup_isbn(isbn):
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
        resp = requests.get(url, timeout=6)
        data = resp.json()
        if data.get("totalItems", 0) == 0:
            return None
        info = data["items"][0]["volumeInfo"]
        authors = info.get("authors", [])
        # API returns "First Last"; convert each to "Last, First"
        author = " / ".join(to_last_first(a) for a in authors) if authors else ""
        categories = info.get("categories", [])
        genre = categories[0] if categories else ""
        return {"title": info.get("title", ""), "author": author, "genre": genre}
    except Exception:
        return None


# ── Date helpers ──────────────────────────────────────────────────────────────
def parse_date_mmddyyyy(s):
    s = s.strip()
    try:
        dt = datetime.strptime(s, "%m/%d/%Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return None


def format_date_mmddyyyy(iso_str):
    if not iso_str:
        return ""
    try:
        dt = datetime.strptime(iso_str, "%Y-%m-%d")
        return dt.strftime("%m/%d/%Y")
    except ValueError:
        return iso_str


# ── Validation helper ─────────────────────────────────────────────────────────
def highlight_required(entry_widget, valid):
    """Set entry border red if invalid, reset if valid."""
    if valid:
        entry_widget.configure(border_color=("gray50", "gray30"))
    else:
        entry_widget.configure(border_color="#e63946")


# ── Book Form Window ──────────────────────────────────────────────────────────
class BookFormWindow(ctk.CTkToplevel):
    def __init__(self, parent, on_save, book=None):
        super().__init__(parent)
        self.on_save = on_save
        self.book = book
        self._invoice_no = None
        self._lookup_in_progress = False
        self.title("Edit Book" if book else "Add Book")
        self.geometry("520x520")
        self.resizable(False, False)
        self.grab_set()
        self._build_ui()
        if book:
            self._populate(book)

    def _build_ui(self):
        pad = {"padx": 20, "pady": 6}

        isbn_frame = ctk.CTkFrame(self, fg_color="transparent")
        isbn_frame.pack(fill="x", **pad)
        ctk.CTkLabel(isbn_frame, text="ISBN", width=100, anchor="w").pack(side="left")
        self.isbn_var = ctk.StringVar()
        self.isbn_entry = ctk.CTkEntry(isbn_frame, textvariable=self.isbn_var, width=240,
                                       placeholder_text="Scan or type ISBN…")
        self.isbn_entry.pack(side="left", padx=(0, 8))
        self.lookup_btn = ctk.CTkButton(isbn_frame, text="Look Up", width=90,
                                        command=self._start_lookup)
        self.lookup_btn.pack(side="left")
        self.isbn_entry.bind("<Return>", lambda e: self._start_lookup())

        self.status_label = ctk.CTkLabel(self, text="", text_color="gray", anchor="w")
        self.status_label.pack(fill="x", padx=20)

        for label, var_name, placeholder in [
            ("Title *",          "title_var",    "Title of the book"),
            ("Author * (Last, First)", "author_var", "e.g. King, Stephen"),
            ("Location",         "location_var", "e.g. Shelf B3"),
        ]:
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", **pad)
            ctk.CTkLabel(row, text=label, width=160, anchor="w").pack(side="left")
            var = ctk.StringVar()
            setattr(self, var_name, var)
            entry = ctk.CTkEntry(row, textvariable=var, width=320,
                                 placeholder_text=placeholder)
            entry.pack(side="left")
            if var_name == "title_var":
                self.title_entry = entry
            elif var_name == "author_var":
                self.author_entry = entry

        genre_row = ctk.CTkFrame(self, fg_color="transparent")
        genre_row.pack(fill="x", **pad)
        ctk.CTkLabel(genre_row, text="Genre", width=100, anchor="w").pack(side="left")
        self.genre_entry = GenreEntry(genre_row, width=340)
        self.genre_entry.pack(side="left")

        price_row = ctk.CTkFrame(self, fg_color="transparent")
        price_row.pack(fill="x", **pad)
        ctk.CTkLabel(price_row, text="Price ($) *", width=100, anchor="w").pack(side="left")
        self.price_var = ctk.StringVar()
        self.price_entry = ctk.CTkEntry(price_row, textvariable=self.price_var, width=100,
                                        placeholder_text="0.00")
        self.price_entry.pack(side="left")

        if not self.book:
            self._invoice_no = get_next_invoice()
            ctk.CTkLabel(self, text=f"Invoice #: {self._invoice_no}",
                         text_color="gray", anchor="w").pack(fill="x", padx=20, pady=(4, 0))

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=20)
        ctk.CTkButton(btn_frame, text="Save Book", command=self._save,
                      fg_color="#2a9d8f", hover_color="#21867a").pack(side="left", padx=(0, 10))
        ctk.CTkButton(btn_frame, text="Cancel", command=self._cancel,
                      fg_color="gray30", hover_color="gray40").pack(side="left")
        self.after(100, self.isbn_entry.focus_set)

    def _populate(self, book):
        self.isbn_var.set(book.get("isbn", "") or "")
        self.title_var.set(book.get("title", "") or "")
        self.author_var.set(book.get("author", "") or "")
        self.genre_entry.set(book.get("genre", "") or "")
        self.price_var.set(str(book.get("price", "")) or "")
        self.location_var.set(book.get("location", "") or "")

    def _start_lookup(self):
        isbn = self.isbn_var.get().strip()
        if not isbn or self._lookup_in_progress:
            return
        self._lookup_in_progress = True
        self.lookup_btn.configure(state="disabled", text="Looking up…")
        self.status_label.configure(text="Searching Google Books…", text_color="gray")
        threading.Thread(target=self._do_lookup, args=(isbn,), daemon=True).start()

    def _do_lookup(self, isbn):
        result = lookup_isbn(isbn)
        self.after(0, self._on_lookup_done, result)

    def _on_lookup_done(self, result):
        self._lookup_in_progress = False
        self.lookup_btn.configure(state="normal", text="Look Up")
        if result:
            self.title_var.set(result["title"])
            self.author_var.set(result["author"])
            self.genre_entry.set(result["genre"])
            self.status_label.configure(
                text="✓ Book found! Review and adjust fields if needed.",
                text_color="#2a9d8f")
        else:
            self.status_label.configure(
                text="No match found. Please fill in fields manually.",
                text_color="#e9c46a")

    def _save(self):
        valid = True

        title = self.title_var.get().strip()
        if not title:
            highlight_required(self.title_entry, False)
            valid = False
        else:
            highlight_required(self.title_entry, True)

        author = self.author_var.get().strip()
        if not validate_last_first(author):
            highlight_required(self.author_entry, False)
            valid = False
        else:
            highlight_required(self.author_entry, True)

        price_str = self.price_var.get().strip()
        try:
            price = float(price_str)
            if price <= 0:
                raise ValueError
            highlight_required(self.price_entry, True)
        except ValueError:
            highlight_required(self.price_entry, False)
            valid = False

        if not valid:
            messagebox.showwarning("Missing Fields",
                                   "Please fix the highlighted fields.\n\nAuthor must be in \"Last, First\" format.",
                                   parent=self)
            return

        genre_val = self.genre_entry.get()
        ensure_genre(genre_val)
        if self.book:
            update_book(self.book["id"], self.isbn_var.get().strip(), title,
                        self.author_var.get().strip(), genre_val,
                        price, self.location_var.get().strip())
        else:
            save_book(self._invoice_no, self.isbn_var.get().strip(), title,
                      self.author_var.get().strip(), genre_val,
                      price, self.location_var.get().strip())
        self.on_save()
        self._check_wants(title, self.author_var.get().strip(),
                          self.isbn_var.get().strip())
        self.destroy()

    def _check_wants(self, title, author, isbn):
        matches = check_wants(title, author, isbn)
        if not matches:
            return
        lines = []
        for cust_name, wid, wtitle, wauthor, wisbn, wnotes, wdate in matches:
            detail = " / ".join(filter(None, [wtitle, wauthor, wisbn]))
            lines.append(f"• {cust_name}  —  wants: {detail}"
                         + (f"\n  Notes: {wnotes}" if wnotes else ""))
        msg = ("A customer has this book on their wants list!\n\n"
               + "\n".join(lines))
        messagebox.showinfo("Want List Match!", msg, parent=self.master)

    def _cancel(self):
        if not self.book and self._invoice_no:
            revert_invoice()
        self.destroy()


# ── Credit Window ─────────────────────────────────────────────────────────────
class CreditWindow(ctk.CTkToplevel):
    def __init__(self, parent, customer, on_save):
        super().__init__(parent)
        self.customer = customer
        self.on_save = on_save
        self.title(f"Store Credit — {customer['name']}")
        self.geometry("460x460")
        self.resizable(False, False)
        self.grab_set()
        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 20, "pady": 6}
        reg = self.customer.get("store_credit", 0.0) or 0.0
        col = self.customer.get("collectible_credit", 0.0) or 0.0

        bal_frame = ctk.CTkFrame(self, fg_color="gray20", corner_radius=8)
        bal_frame.pack(fill="x", padx=20, pady=(16, 4))
        ctk.CTkLabel(bal_frame, text=f"Regular Credit: ${reg:.2f}",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#2a9d8f").pack(side="left", padx=16, pady=10)
        ctk.CTkLabel(bal_frame, text=f"Collectible Credit: ${col:.2f}",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#e9c46a").pack(side="left", padx=16, pady=10)

        amt_row = ctk.CTkFrame(self, fg_color="transparent")
        amt_row.pack(fill="x", **pad)
        ctk.CTkLabel(amt_row, text="Amount ($)", width=120, anchor="w").pack(side="left")
        self.amount_var = ctk.StringVar()
        ctk.CTkEntry(amt_row, textvariable=self.amount_var, width=120,
                     placeholder_text="e.g. 5.00").pack(side="left")

        type_row = ctk.CTkFrame(self, fg_color="transparent")
        type_row.pack(fill="x", **pad)
        ctk.CTkLabel(type_row, text="Type", width=120, anchor="w").pack(side="left")
        self.type_var = ctk.StringVar(value="Add (Donation)")
        ctk.CTkComboBox(type_row, variable=self.type_var,
                        values=["Add (Donation)", "Spend (Purchase)"],
                        width=180, state="readonly").pack(side="left")

        coll_row = ctk.CTkFrame(self, fg_color="transparent")
        coll_row.pack(fill="x", **pad)
        ctk.CTkLabel(coll_row, text="", width=120).pack(side="left")
        self.coll_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(coll_row, text="Collectible Credit",
                        variable=self.coll_var).pack(side="left")

        note_row = ctk.CTkFrame(self, fg_color="transparent")
        note_row.pack(fill="x", **pad)
        ctk.CTkLabel(note_row, text="Note", width=120, anchor="w").pack(side="left")
        self.note_var = ctk.StringVar()
        ctk.CTkEntry(note_row, textvariable=self.note_var, width=240,
                     placeholder_text="e.g. Donated 3 books").pack(side="left")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=12)
        ctk.CTkButton(btn_frame, text="Save Transaction", command=self._save,
                      fg_color="#2a9d8f", hover_color="#21867a").pack(side="left", padx=(0, 10))
        ctk.CTkButton(btn_frame, text="Cancel", command=self.destroy,
                      fg_color="gray30", hover_color="gray40").pack(side="left")

        ctk.CTkLabel(self, text="Transaction History",
                     font=ctk.CTkFont(weight="bold"), anchor="w").pack(
            fill="x", padx=20, pady=(8, 2))
        log_frame = ctk.CTkFrame(self)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        cols = ("date", "amount", "type", "note")
        self.log_tree = ttk.Treeview(log_frame, columns=cols, show="headings", height=6)
        self.log_tree.heading("date",   text="Date")
        self.log_tree.heading("amount", text="Amount")
        self.log_tree.heading("type",   text="Type")
        self.log_tree.heading("note",   text="Note")
        self.log_tree.column("date",   width=130)
        self.log_tree.column("amount", width=75)
        self.log_tree.column("type",   width=90)
        self.log_tree.column("note",   width=160)
        self.log_tree.pack(fill="both", expand=True)
        self._refresh_log()

    def _refresh_log(self):
        for item in self.log_tree.get_children():
            self.log_tree.delete(item)
        for date_str, amount, credit_type, note in get_credit_log(self.customer["id"]):
            prefix = "+" if amount >= 0 else ""
            self.log_tree.insert("", "end",
                                 values=(date_str, f"{prefix}${amount:.2f}",
                                         credit_type or "regular", note or ""))

    def _save(self):
        try:
            amount = float(self.amount_var.get().strip())
        except ValueError:
            messagebox.showwarning("Invalid Amount", "Please enter a valid dollar amount.",
                                   parent=self)
            return
        if amount <= 0:
            messagebox.showwarning("Invalid Amount", "Amount must be greater than zero.",
                                   parent=self)
            return
        credit_type = "collectible" if self.coll_var.get() else "regular"
        if "Spend" in self.type_var.get():
            current = get_customer(self.customer["id"])
            balance = current["collectible_credit"] if credit_type == "collectible" \
                else current["store_credit"]
            if amount > (balance or 0):
                messagebox.showwarning("Insufficient Credit",
                                       f"Only ${balance:.2f} in {credit_type} credit.",
                                       parent=self)
                return
            amount = -amount
        add_credit_transaction(self.customer["id"], amount,
                               self.note_var.get().strip(), credit_type)
        self.amount_var.set("")
        self.note_var.set("")
        self.customer = get_customer(self.customer["id"])
        self.on_save()
        self._refresh_log()
        reg = self.customer.get("store_credit", 0.0) or 0.0
        col = self.customer.get("collectible_credit", 0.0) or 0.0
        messagebox.showinfo("Saved",
                            f"Transaction saved.\nRegular: ${reg:.2f} | Collectible: ${col:.2f}",
                            parent=self)


# ── Customer Form Window ──────────────────────────────────────────────────────
class CustomerFormWindow(ctk.CTkToplevel):
    def __init__(self, parent, on_save, customer=None):
        super().__init__(parent)
        self.on_save = on_save
        self.customer = customer
        self.title("Edit Customer" if customer else "Add Customer")
        self.geometry("520x500")
        self.resizable(False, False)
        self.grab_set()
        self._build_ui()
        if customer:
            self._populate(customer)

    def _build_ui(self):
        pad = {"padx": 20, "pady": 6}

        name_row = ctk.CTkFrame(self, fg_color="transparent")
        name_row.pack(fill="x", **pad)
        ctk.CTkLabel(name_row, text="Name * (Last, First)",
                     width=150, anchor="w").pack(side="left")
        self.name_var = ctk.StringVar()
        self.name_entry = ctk.CTkEntry(name_row, textvariable=self.name_var, width=300,
                                       placeholder_text="e.g. Smith, John")
        self.name_entry.pack(side="left")

        phone_row = ctk.CTkFrame(self, fg_color="transparent")
        phone_row.pack(fill="x", **pad)
        ctk.CTkLabel(phone_row, text="Phone", width=150, anchor="w").pack(side="left")
        self.phone_var = ctk.StringVar()
        phone_entry = ctk.CTkEntry(phone_row, textvariable=self.phone_var, width=200,
                                   placeholder_text="Numbers only")
        phone_entry.pack(side="left")
        vcmd = (self.register(lambda s: s.isdigit() or s == ""), "%S")
        phone_entry.configure(validate="key", validatecommand=vcmd)

        email_row = ctk.CTkFrame(self, fg_color="transparent")
        email_row.pack(fill="x", **pad)
        ctk.CTkLabel(email_row, text="Email", width=150, anchor="w").pack(side="left")
        self.email_var = ctk.StringVar()
        ctk.CTkEntry(email_row, textvariable=self.email_var, width=300,
                     placeholder_text="Email address").pack(side="left")

        deros_row = ctk.CTkFrame(self, fg_color="transparent")
        deros_row.pack(fill="x", **pad)
        ctk.CTkLabel(deros_row, text="DEROS", width=150, anchor="w").pack(side="left")
        self.deros_month_var = ctk.StringVar(value="Month")
        self.deros_year_var = ctk.StringVar(value="Year")
        self.indefinite_var = ctk.BooleanVar(value=True)
        self.deros_month_cb = ctk.CTkComboBox(deros_row, variable=self.deros_month_var,
                                              values=MONTH_NAMES, width=120,
                                              state="readonly")
        self.deros_month_cb.pack(side="left", padx=(0, 6))
        self.deros_year_cb = ctk.CTkComboBox(deros_row, variable=self.deros_year_var,
                                             values=YEAR_RANGE, width=90,
                                             state="readonly")
        self.deros_year_cb.pack(side="left", padx=(0, 10))
        ctk.CTkCheckBox(deros_row, text="Indefinite",
                        variable=self.indefinite_var,
                        command=self._toggle_deros).pack(side="left")
        self._toggle_deros()

        pc_row = ctk.CTkFrame(self, fg_color="transparent")
        pc_row.pack(fill="x", **pad)
        ctk.CTkLabel(pc_row, text="Pref. Contact", width=150, anchor="w").pack(side="left")
        self.contact_var = ctk.StringVar(value="Phone")
        ctk.CTkComboBox(pc_row, variable=self.contact_var,
                        values=["Phone", "Email", "Facebook", "Instagram"],
                        width=160, state="readonly",
                        command=self._toggle_handle).pack(side="left")

        self.handle_row = ctk.CTkFrame(self, fg_color="transparent")
        self.handle_row.pack(fill="x", **pad)
        ctk.CTkLabel(self.handle_row, text="Handle / Profile Name", width=150,
                     anchor="w").pack(side="left")
        self.handle_var = ctk.StringVar()
        ctk.CTkEntry(self.handle_row, textvariable=self.handle_var, width=300,
                     placeholder_text="@username or profile URL").pack(side="left")
        self._toggle_handle(self.contact_var.get())

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=20)
        ctk.CTkButton(btn_frame, text="Save Customer", command=self._save,
                      fg_color="#2a9d8f", hover_color="#21867a").pack(side="left", padx=(0, 10))
        ctk.CTkButton(btn_frame, text="Cancel", command=self.destroy,
                      fg_color="gray30", hover_color="gray40").pack(side="left")

    def _toggle_deros(self):
        state = "disabled" if self.indefinite_var.get() else "readonly"
        self.deros_month_cb.configure(state=state)
        self.deros_year_cb.configure(state=state)

    def _toggle_handle(self, value):
        if value in ("Facebook", "Instagram"):
            self.handle_row.pack(fill="x", padx=20, pady=6)
        else:
            self.handle_row.pack_forget()

    def _populate(self, c):
        self.name_var.set(c.get("name", "") or "")
        self.phone_var.set(c.get("phone", "") or "")
        self.email_var.set(c.get("email", "") or "")
        deros = c.get("deros_date", "") or ""
        if deros and deros != "Indefinite":
            parts = deros.split("-")
            if len(parts) == 2:
                try:
                    month_idx = int(parts[1]) - 1
                    self.deros_month_var.set(MONTH_NAMES[month_idx])
                    self.deros_year_var.set(parts[0])
                    self.indefinite_var.set(False)
                except Exception:
                    self.indefinite_var.set(True)
            else:
                self.indefinite_var.set(True)
        else:
            self.indefinite_var.set(True)
        self.contact_var.set(c.get("preferred_contact", "Phone") or "Phone")
        self.handle_var.set(c.get("social_handle", "") or "")
        self._toggle_handle(self.contact_var.get())
        self._toggle_deros()

    def _get_deros(self):
        if self.indefinite_var.get():
            return "Indefinite"
        month = self.deros_month_var.get()
        year = self.deros_year_var.get()
        if month == "Month" or year == "Year":
            return ""
        month_num = MONTH_NAMES.index(month) + 1
        return f"{year}-{month_num:02d}"

    def _save(self):
        valid = True
        name = self.name_var.get().strip()
        if not validate_last_first(name):
            highlight_required(self.name_entry, False)
            valid = False
        else:
            highlight_required(self.name_entry, True)

        if not valid:
            messagebox.showwarning("Missing Fields",
                                   "Please fix the highlighted fields.\n\nName must be in \"Last, First\" format.",
                                   parent=self)
            return

        deros = self._get_deros()
        if self.customer:
            update_customer(self.customer["id"], name, self.phone_var.get().strip(),
                            self.email_var.get().strip(), deros,
                            self.contact_var.get(), self.handle_var.get().strip())
        else:
            save_customer(name, self.phone_var.get().strip(),
                          self.email_var.get().strip(), deros,
                          self.contact_var.get(), self.handle_var.get().strip())
        self.on_save()
        self.destroy()


# ── Customer Picker ───────────────────────────────────────────────────────────
class CustomerPickerWindow(ctk.CTkToplevel):
    def __init__(self, parent, on_select):
        super().__init__(parent)
        self.on_select = on_select
        self.title("Find Customer")
        self.geometry("540x420")
        self.grab_set()
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(self, text="Find Customer",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(16, 4))
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(top, text="Search:").pack(side="left", padx=(0, 8))
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh())
        search_entry = ctk.CTkEntry(top, textvariable=self.search_var,
                                    placeholder_text="Name, phone, or email…", width=300)
        search_entry.pack(side="left")
        self.after(100, search_entry.focus_set)

        table_frame = ctk.CTkFrame(self)
        table_frame.pack(fill="both", expand=True, padx=16)
        cols = ("name", "phone", "email", "reg_credit", "coll_credit")
        self.tree = ttk.Treeview(table_frame, columns=cols,
                                  show="headings", selectmode="browse")
        self.tree.heading("name",        text="Name")
        self.tree.heading("phone",       text="Phone")
        self.tree.heading("email",       text="Email")
        self.tree.heading("reg_credit",  text="Regular Credit")
        self.tree.heading("coll_credit", text="Coll. Credit")
        self.tree.column("name",        width=150)
        self.tree.column("phone",       width=100)
        self.tree.column("email",       width=150)
        self.tree.column("reg_credit",  width=100)
        self.tree.column("coll_credit", width=90)

        style = ttk.Style()
        style.configure("Treeview", background="#2b2b2b", foreground="white",
                        fieldbackground="#2b2b2b", rowheight=26, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#1f538d", foreground="white",
                        font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#1f538d")])

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._select)
        self._refresh()

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=12)
        ctk.CTkButton(btn_frame, text="✓ Select Customer", command=self._select,
                      fg_color="#2a9d8f", hover_color="#21867a").pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_frame, text="Guest (No Account)", command=self._guest,
                      fg_color="gray30", hover_color="gray40").pack(side="left")

    def _refresh(self):
        rows = get_all_customers(self.search_var.get().strip())
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in rows:
            cid, name, phone, email, *_, reg_credit, coll_credit = row
            self.tree.insert("", "end", iid=str(cid),
                             values=(name, phone or "", email or "",
                                     f"${reg_credit:.2f}" if reg_credit else "$0.00",
                                     f"${coll_credit:.2f}" if coll_credit else "$0.00"))

    def _select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Please select a customer.", parent=self)
            return
        self.on_select(get_customer(int(sel[0])))
        self.destroy()

    def _guest(self):
        self.on_select(None)
        self.destroy()


# ── Checkout Tab ──────────────────────────────────────────────────────────────
class CheckoutFrame(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self.cart = []
        self.customer = None
        self._build_ui()
        self._refresh_banners()

    def _build_ui(self):
        left = ctk.CTkFrame(self)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self.daily_banner = ctk.CTkLabel(left, text="",
                                         font=ctk.CTkFont(size=12, weight="bold"),
                                         fg_color="#1f538d", corner_radius=6)
        self.daily_banner.pack(fill="x", padx=4, pady=(4, 2))

        self.monthly_banner = ctk.CTkLabel(left, text="",
                                           font=ctk.CTkFont(size=11),
                                           fg_color="gray25", corner_radius=6,
                                           wraplength=600, justify="left")
        self.monthly_banner.pack(fill="x", padx=4, pady=(0, 8))

        entry_row = ctk.CTkFrame(left, fg_color="transparent")
        entry_row.pack(fill="x", padx=4, pady=(0, 8))
        ctk.CTkLabel(entry_row, text="Invoice #:", width=80, anchor="w").pack(side="left")
        self.invoice_entry_var = ctk.StringVar()
        self.invoice_entry = ctk.CTkEntry(entry_row, textvariable=self.invoice_entry_var,
                                          width=140, placeholder_text="Scan or type…")
        self.invoice_entry.pack(side="left", padx=(0, 8))
        self.invoice_entry.bind("<Return>", lambda e: self._add_to_cart())
        ctk.CTkButton(entry_row, text="Add to Cart", width=110,
                      fg_color="#2a9d8f", hover_color="#21867a",
                      command=self._add_to_cart).pack(side="left")

        self.add_status = ctk.CTkLabel(left, text="", text_color="gray", anchor="w")
        self.add_status.pack(fill="x", padx=4)

        cart_frame = ctk.CTkFrame(left)
        cart_frame.pack(fill="both", expand=True, padx=4, pady=(4, 0))
        cols = ("invoice", "title", "genre", "orig", "disc", "final")
        self.cart_tree = ttk.Treeview(cart_frame, columns=cols, show="headings")
        self.cart_tree.heading("invoice", text="Invoice #")
        self.cart_tree.heading("title",   text="Title")
        self.cart_tree.heading("genre",   text="Genre")
        self.cart_tree.heading("orig",    text="Original")
        self.cart_tree.heading("disc",    text="Discount")
        self.cart_tree.heading("final",   text="Final")
        self.cart_tree.column("invoice", width=75)
        self.cart_tree.column("title",   width=200)
        self.cart_tree.column("genre",   width=110)
        self.cart_tree.column("orig",    width=70)
        self.cart_tree.column("disc",    width=80)
        self.cart_tree.column("final",   width=70)

        style = ttk.Style()
        style.configure("Treeview", background="#2b2b2b", foreground="white",
                        fieldbackground="#2b2b2b", rowheight=26, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#1f538d", foreground="white",
                        font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#1f538d")])

        vsb = ttk.Scrollbar(cart_frame, orient="vertical", command=self.cart_tree.yview)
        self.cart_tree.configure(yscrollcommand=vsb.set)
        self.cart_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        ctk.CTkButton(left, text="✕  Remove Selected", width=160,
                      fg_color="#e63946", hover_color="#c1121f",
                      command=self._remove_from_cart).pack(anchor="w", padx=4, pady=6)

        right = ctk.CTkFrame(self, width=280)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        ctk.CTkLabel(right, text="Checkout Summary",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(16, 8))

        cust_frame = ctk.CTkFrame(right, fg_color="gray20", corner_radius=8)
        cust_frame.pack(fill="x", padx=12, pady=(0, 8))
        self.cust_label = ctk.CTkLabel(cust_frame, text="No customer linked",
                                       text_color="gray", wraplength=220)
        self.cust_label.pack(padx=10, pady=6)
        ctk.CTkButton(cust_frame, text="Link Customer", width=180,
                      command=self._link_customer).pack(padx=10, pady=(0, 8))

        totals_frame = ctk.CTkFrame(right, fg_color="gray20", corner_radius=8)
        totals_frame.pack(fill="x", padx=12, pady=(0, 8))
        for label, attr in [("Subtotal:", "subtotal_label"),
                             ("Discounts:", "discount_label"),
                             ("Total:", "total_label")]:
            row = ctk.CTkFrame(totals_frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(row, text=label, width=90, anchor="w").pack(side="left")
            lbl = ctk.CTkLabel(row, text="$0.00", anchor="e")
            setattr(self, attr, lbl)
            lbl.pack(side="right")

        self.credit_avail_label = ctk.CTkLabel(right, text="",
                                                text_color="#2a9d8f", wraplength=240)
        self.credit_avail_label.pack()

        pay_frame = ctk.CTkFrame(right, fg_color="gray20", corner_radius=8)
        pay_frame.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(pay_frame, text="Payment",
                     font=ctk.CTkFont(weight="bold")).pack(pady=(8, 4))
        for label, var_name in [("Cash ($):",         "pay_cash_var"),
                                 ("Card ($):",         "pay_card_var"),
                                 ("Reg. Credit ($):",  "pay_credit_var"),
                                 ("Coll. Credit ($):", "pay_coll_credit_var")]:
            row = ctk.CTkFrame(pay_frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(row, text=label, width=110, anchor="w").pack(side="left")
            var = ctk.StringVar(value="0.00")
            setattr(self, var_name, var)
            ctk.CTkEntry(row, textvariable=var, width=80).pack(side="right")

        ctk.CTkButton(right, text="✓  Complete Sale", height=40,
                      fg_color="#2a9d8f", hover_color="#21867a",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._complete_sale).pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkButton(right, text="Clear Cart", fg_color="gray30", hover_color="gray40",
                      command=self._clear_cart).pack(fill="x", padx=12)

        self.after(200, self.invoice_entry.focus_set)

    def _refresh_banners(self):
        daily_text, monthly_text = get_todays_banners()
        self.daily_banner.configure(
            text=f"🏷  {daily_text}",
            text_color="white" if "—" in daily_text else "gray")
        if monthly_text:
            self.monthly_banner.configure(text=f"📅  {monthly_text}", text_color="white")
        else:
            self.monthly_banner.configure(text="", text_color="gray")

    def _add_to_cart(self):
        raw = self.invoice_entry_var.get().strip()
        if not raw:
            return
        try:
            inv_no = int(raw)
            if inv_no <= 0:
                raise ValueError
        except ValueError:
            self.add_status.configure(
                text="Invoice # must be a positive whole number.", text_color="#e63946")
            return

        if any(item["invoice_no"] == inv_no for item in self.cart):
            self.add_status.configure(text="Already in cart.", text_color="#e9c46a")
            self.invoice_entry_var.set("")
            return

        book = get_book_by_invoice(inv_no)
        if not book:
            self.add_status.configure(text=f"No book found with invoice #{inv_no}.",
                                      text_color="#e63946")
            return

        disc_pct, disc_label = get_discount_for_book(book)
        orig_price = book["price"] or 0.0
        final_price = round(orig_price * (1 - disc_pct / 100), 2)

        self.cart.append({
            "invoice_no":   inv_no,
            "title":        book["title"],
            "genre":        book.get("genre") or "",
            "orig_price":   orig_price,
            "discount_pct": disc_pct,
            "disc_label":   disc_label,
            "final_price":  final_price,
        })
        self._refresh_cart_table()
        self.invoice_entry_var.set("")
        status = f"✓ Added: {book['title']}"
        if disc_pct > 0:
            status += f"  [{disc_label}]"
        self.add_status.configure(text=status, text_color="#2a9d8f")
        self.invoice_entry.focus_set()

    def _refresh_cart_table(self):
        for item in self.cart_tree.get_children():
            self.cart_tree.delete(item)
        subtotal = 0.0
        discount_total = 0.0
        for i, item in enumerate(self.cart):
            disc_str = f"{item['discount_pct']:.0f}%" if item["discount_pct"] > 0 else "—"
            self.cart_tree.insert("", "end", iid=str(i),
                                  values=(item["invoice_no"], item["title"], item["genre"],
                                          f"${item['orig_price']:.2f}", disc_str,
                                          f"${item['final_price']:.2f}"))
            subtotal += item["orig_price"]
            discount_total += item["orig_price"] - item["final_price"]

        total = subtotal - discount_total
        self.subtotal_label.configure(text=f"${subtotal:.2f}")
        self.discount_label.configure(
            text=f"-${discount_total:.2f}",
            text_color="#2a9d8f" if discount_total > 0 else "white")
        self.total_label.configure(text=f"${total:.2f}",
                                   font=ctk.CTkFont(size=13, weight="bold"))

    def _remove_from_cart(self):
        sel = self.cart_tree.selection()
        if not sel:
            return
        self.cart.pop(int(sel[0]))
        self._refresh_cart_table()
        self.add_status.configure(text="Item removed.", text_color="gray")

    def _link_customer(self):
        CustomerPickerWindow(self, on_select=self._on_customer_selected)

    def _on_customer_selected(self, customer):
        self.customer = customer
        if customer:
            reg = customer.get("store_credit", 0.0) or 0.0
            col = customer.get("collectible_credit", 0.0) or 0.0
            self.cust_label.configure(
                text=f"👤 {customer['name']}\nReg: ${reg:.2f}  |  Coll: ${col:.2f}",
                text_color="white")
            self.credit_avail_label.configure(
                text=f"Regular: ${reg:.2f}  |  Collectible: ${col:.2f}")
        else:
            self.cust_label.configure(text="Guest (no account)", text_color="gray")
            self.credit_avail_label.configure(text="")

    def _clear_cart(self):
        self.cart = []
        self.customer = None
        self.cust_label.configure(text="No customer linked", text_color="gray")
        self.credit_avail_label.configure(text="")
        self.pay_cash_var.set("0.00")
        self.pay_card_var.set("0.00")
        self.pay_credit_var.set("0.00")
        self.pay_coll_credit_var.set("0.00")
        self.add_status.configure(text="")
        self._refresh_cart_table()

    def _complete_sale(self):
        if not self.cart:
            messagebox.showwarning("Empty Cart",
                                   "Add at least one book before completing the sale.")
            return

        subtotal = sum(i["orig_price"] for i in self.cart)
        discount_total = sum(i["orig_price"] - i["final_price"] for i in self.cart)
        total = subtotal - discount_total

        try:
            pay_cash        = float(self.pay_cash_var.get() or 0)
            pay_card        = float(self.pay_card_var.get() or 0)
            pay_credit      = float(self.pay_credit_var.get() or 0)
            pay_coll_credit = float(self.pay_coll_credit_var.get() or 0)
        except ValueError:
            messagebox.showwarning("Invalid Payment", "Please enter valid payment amounts.")
            return

        payment_sum = round(pay_cash + pay_card + pay_credit + pay_coll_credit, 2)
        if payment_sum < round(total, 2):
            messagebox.showwarning(
                "Underpayment",
                f"Payment (${payment_sum:.2f}) is less than total (${total:.2f}).")
            return

        if pay_credit > 0 or pay_coll_credit > 0:
            if not self.customer:
                messagebox.showwarning("No Customer",
                                       "A customer must be linked to use store credit.")
                return
            current = get_customer(self.customer["id"])
            if pay_credit > (current.get("store_credit") or 0):
                messagebox.showwarning(
                    "Insufficient Credit",
                    f"Only ${current['store_credit']:.2f} regular credit available.")
                return
            if pay_coll_credit > 0:
                non_coll = [i for i in self.cart
                            if not any(g.lower() in (i["genre"] or "").lower()
                                       for g in COLLECTIBLE_GENRES)]
                if non_coll:
                    messagebox.showwarning(
                        "Invalid Use",
                        "Collectible credit can only be used on Collectibles/Specialty books.\n"
                        "Your cart contains non-collectible items.")
                    return
                if pay_coll_credit > (current.get("collectible_credit") or 0):
                    messagebox.showwarning(
                        "Insufficient Credit",
                        f"Only ${current['collectible_credit']:.2f} collectible credit available.")
                    return

        if not messagebox.askyesno(
                "Complete Sale",
                f"Total: ${total:.2f}\n"
                f"Cash: ${pay_cash:.2f}  Card: ${pay_card:.2f}\n"
                f"Reg Credit: ${pay_credit:.2f}  Coll Credit: ${pay_coll_credit:.2f}\n\n"
                f"Complete this sale?"):
            return

        customer_id = self.customer["id"] if self.customer else None
        save_sale(customer_id, self.cart, subtotal, discount_total, total,
                  pay_cash, pay_card, pay_credit + pay_coll_credit)

        for item in self.cart:
            reduce_inventory(item["invoice_no"])

        if pay_credit > 0 and self.customer:
            add_credit_transaction(customer_id, -pay_credit,
                                   f"Used in sale — {date.today()}", "regular")
        if pay_coll_credit > 0 and self.customer:
            add_credit_transaction(customer_id, -pay_coll_credit,
                                   f"Used in sale — {date.today()}", "collectible")

        change = round(payment_sum - total, 2)
        change_str = f"\n\nChange due: ${change:.2f}" if pay_cash > 0 and change > 0 else ""
        messagebox.showinfo("Sale Complete",
                            f"✓ Sale completed!\nTotal: ${total:.2f}{change_str}")
        self._clear_cart()
        self._refresh_banners()


# ── Special Sales Tab ─────────────────────────────────────────────────────────
class SpecialSalesFrame(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        ctk.CTkLabel(self, text="Special Sales",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(self,
                     text="Schedule one-off sales outside the regular monthly/daily discounts.",
                     text_color="gray").pack(anchor="w", pady=(0, 8))

        form = ctk.CTkFrame(self, fg_color="gray20", corner_radius=8)
        form.pack(fill="x", pady=(0, 12))

        row1 = ctk.CTkFrame(form, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(row1, text="Genre:", width=60, anchor="w").pack(side="left")
        self.genre_entry = GenreEntry(row1, width=160)
        self.genre_entry.pack(side="left", padx=(0, 16))
        ctk.CTkLabel(row1, text="Discount %:", anchor="w").pack(side="left")
        self.pct_var = ctk.StringVar()
        ctk.CTkEntry(row1, textvariable=self.pct_var, width=60,
                     placeholder_text="e.g. 20").pack(side="left", padx=(4, 0))

        row2 = ctk.CTkFrame(form, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(row2, text="Start (MM/DD/YYYY):", width=140, anchor="w").pack(side="left")
        self.start_var = ctk.StringVar()
        self.start_entry = ctk.CTkEntry(row2, textvariable=self.start_var, width=120,
                                        placeholder_text="MM/DD/YYYY")
        self.start_entry.pack(side="left", padx=(0, 20))
        ctk.CTkLabel(row2, text="End (MM/DD/YYYY):", width=130, anchor="w").pack(side="left")
        self.end_var = ctk.StringVar()
        self.end_entry = ctk.CTkEntry(row2, textvariable=self.end_var, width=120,
                                      placeholder_text="MM/DD/YYYY")
        self.end_entry.pack(side="left")

        row3 = ctk.CTkFrame(form, fg_color="transparent")
        row3.pack(fill="x", padx=12, pady=(4, 10))
        ctk.CTkLabel(row3, text="Note:", width=60, anchor="w").pack(side="left")
        self.note_var = ctk.StringVar()
        ctk.CTkEntry(row3, textvariable=self.note_var, width=260,
                     placeholder_text="Optional note").pack(side="left", padx=(0, 12))
        ctk.CTkButton(row3, text="+ Add Sale", fg_color="#2a9d8f", hover_color="#21867a",
                      command=self._add).pack(side="left")

        table_frame = ctk.CTkFrame(self)
        table_frame.pack(fill="both", expand=True)
        cols = ("genre", "pct", "start", "end", "note", "status")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings")
        for col, heading, width in [
            ("genre", "Genre", 140), ("pct", "Discount", 80),
            ("start", "Start Date", 100), ("end", "End Date", 100),
            ("note", "Note", 180), ("status", "Status", 80)]:
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width)
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        ctk.CTkButton(self, text="🗑  Delete Selected",
                      fg_color="#e63946", hover_color="#c1121f",
                      command=self._delete).pack(anchor="w", pady=(8, 0))

    def _add(self):
        genre = self.genre_entry.get()
        start_raw = self.start_var.get().strip()
        end_raw   = self.end_var.get().strip()

        if not genre or not start_raw or not end_raw:
            messagebox.showwarning("Missing Fields",
                                   "Genre, start date, and end date are required.",
                                   parent=self)
            return

        start = parse_date_mmddyyyy(start_raw)
        end   = parse_date_mmddyyyy(end_raw)
        valid = True

        if not start:
            highlight_required(self.start_entry, False)
            valid = False
        else:
            highlight_required(self.start_entry, True)

        if not end:
            highlight_required(self.end_entry, False)
            valid = False
        else:
            highlight_required(self.end_entry, True)

        if not valid:
            messagebox.showwarning("Invalid Date",
                                   "Dates must be in MM/DD/YYYY format.", parent=self)
            return

        try:
            pct = float(self.pct_var.get().strip())
        except ValueError:
            messagebox.showwarning("Invalid", "Please enter a valid percentage.", parent=self)
            return

        ensure_genre(genre)
        save_special_sale(genre, pct, start, end, self.note_var.get().strip())
        self.genre_entry.set("")
        self.pct_var.set("")
        self.start_var.set("")
        self.end_var.set("")
        self.note_var.set("")
        self._refresh()

    def _refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        today = date.today().strftime("%Y-%m-%d")
        for row in get_special_sales():
            sid, genre, pct, start, end, note = row
            if today < start:
                status = "Upcoming"
            elif today > end:
                status = "Expired"
            else:
                status = "Active ✓"
            start_disp = format_date_mmddyyyy(start)
            end_disp   = format_date_mmddyyyy(end)
            self.tree.insert("", "end", iid=str(sid),
                             values=(genre, f"{pct:.0f}%", start_disp, end_disp,
                                     note or "", status))

    def _delete(self):
        sel = self.tree.selection()
        if not sel:
            return
        if messagebox.askyesno("Confirm", "Delete this special sale?", parent=self):
            delete_special_sale(int(sel[0]))
            self._refresh()


# ── Discounts Tab ─────────────────────────────────────────────────────────────
class DiscountsFrame(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._build_ui()

    def _build_ui(self):
        left = ctk.CTkFrame(self)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = ctk.CTkFrame(self)
        right.pack(side="right", fill="both", expand=True)
        self._build_daily(left)
        self._build_monthly(right)

    def _build_daily(self, parent):
        ctk.CTkLabel(parent, text="Daily Discounts",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", padx=12, pady=(12, 4))
        ctk.CTkLabel(parent, text="Select a day to view and edit its genres.",
                     text_color="gray").pack(anchor="w", padx=12, pady=(0, 8))

        day_row = ctk.CTkFrame(parent, fg_color="transparent")
        day_row.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(day_row, text="Day:", width=50, anchor="w").pack(side="left")
        self.selected_day = ctk.StringVar(value="Monday")
        ctk.CTkComboBox(day_row, variable=self.selected_day,
                        values=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"],
                        width=160, state="readonly",
                        command=lambda _: self._refresh_daily()).pack(side="left")

        self.day_name_label = ctk.CTkLabel(parent, text="", text_color="#2a9d8f",
                                            font=ctk.CTkFont(weight="bold"), anchor="w")
        self.day_name_label.pack(fill="x", padx=12, pady=(0, 4))

        table_frame = ctk.CTkFrame(parent)
        table_frame.pack(fill="both", expand=True, padx=12)
        cols = ("genre", "pct")
        self.daily_tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=8)
        self.daily_tree.heading("genre", text="Genre")
        self.daily_tree.heading("pct",   text="Discount %")
        self.daily_tree.column("genre", width=200)
        self.daily_tree.column("pct",   width=90)
        self.daily_tree.pack(fill="both", expand=True)

        edit_frame = ctk.CTkFrame(parent, fg_color="gray20", corner_radius=8)
        edit_frame.pack(fill="x", padx=12, pady=8)
        ctk.CTkLabel(edit_frame, text="Change genre for selected row:",
                     anchor="w").pack(fill="x", padx=10, pady=(8, 4))
        edit_row = ctk.CTkFrame(edit_frame, fg_color="transparent")
        edit_row.pack(fill="x", padx=10, pady=(0, 10))
        self.daily_genre_entry = GenreEntry(edit_row, width=180)
        self.daily_genre_entry.pack(side="left", padx=(0, 8))
        ctk.CTkButton(edit_row, text="Update", width=80,
                      fg_color="#2a9d8f", hover_color="#21867a",
                      command=self._update_daily_genre).pack(side="left")

        add_frame = ctk.CTkFrame(parent, fg_color="gray20", corner_radius=8)
        add_frame.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(add_frame, text="Add genre to this day:",
                     anchor="w").pack(fill="x", padx=10, pady=(8, 4))
        add_row = ctk.CTkFrame(add_frame, fg_color="transparent")
        add_row.pack(fill="x", padx=10, pady=(0, 10))
        self.new_daily_genre_entry = GenreEntry(add_row, width=140)
        self.new_daily_genre_entry.pack(side="left", padx=(0, 6))
        self.new_daily_pct_var = ctk.StringVar(value="25")
        ctk.CTkEntry(add_row, textvariable=self.new_daily_pct_var,
                     width=50).pack(side="left", padx=(0, 4))
        ctk.CTkLabel(add_row, text="%").pack(side="left", padx=(0, 8))
        ctk.CTkButton(add_row, text="Add", width=70,
                      fg_color="#2a9d8f", hover_color="#21867a",
                      command=self._add_daily_genre).pack(side="left", padx=(0, 8))
        ctk.CTkButton(add_row, text="Remove Selected", width=130,
                      fg_color="#e63946", hover_color="#c1121f",
                      command=self._remove_daily_genre).pack(side="left")

        self._refresh_daily()

    def _refresh_daily(self):
        day_name = self.selected_day.get()
        day_map = {"Monday":0,"Tuesday":1,"Wednesday":2,
                   "Thursday":3,"Friday":4,"Saturday":5}
        day_num = day_map.get(day_name, 0)
        rows = get_daily_discounts_for_day(day_num)
        for item in self.daily_tree.get_children():
            self.daily_tree.delete(item)
        themed = rows[0][1] if rows else day_name
        self.day_name_label.configure(
            text=f"Theme: {themed}" if rows else "No discounts set")
        for did, dname, genre, pct in rows:
            self.daily_tree.insert("", "end", iid=str(did),
                                   values=(genre, f"{pct:.0f}%"))

    def _update_daily_genre(self):
        sel = self.daily_tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Select a genre row to update.", parent=self)
            return
        new_genre = self.daily_genre_entry.get()
        if not new_genre:
            messagebox.showwarning("Missing", "Enter a new genre name.", parent=self)
            return
        update_daily_discount_genre(int(sel[0]), new_genre)
        self.daily_genre_entry.set("")
        self._refresh_daily()

    def _add_daily_genre(self):
        day_name = self.selected_day.get()
        day_map = {"Monday":0,"Tuesday":1,"Wednesday":2,
                   "Thursday":3,"Friday":4,"Saturday":5}
        day_num = day_map.get(day_name, 0)
        genre = self.new_daily_genre_entry.get()
        if not genre:
            messagebox.showwarning("Missing", "Enter a genre name.", parent=self)
            return
        try:
            pct = float(self.new_daily_pct_var.get().strip())
        except ValueError:
            messagebox.showwarning("Invalid", "Enter a valid percentage.", parent=self)
            return
        rows = get_daily_discounts_for_day(day_num)
        themed_name = rows[0][1] if rows else day_name
        ensure_genre(genre)
        add_daily_discount(day_num, themed_name, genre, pct)
        self.new_daily_genre_entry.set("")
        self.new_daily_pct_var.set("25")
        self._refresh_daily()

    def _remove_daily_genre(self):
        sel = self.daily_tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Select a genre to remove.", parent=self)
            return
        if messagebox.askyesno("Confirm", "Remove this genre from the daily discount?",
                               parent=self):
            delete_daily_discount(int(sel[0]))
            self._refresh_daily()

    def _build_monthly(self, parent):
        ctk.CTkLabel(parent, text="Monthly Discounts",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", padx=12, pady=(12, 4))
        ctk.CTkLabel(parent, text="Select a month to view and edit its genres.",
                     text_color="gray").pack(anchor="w", padx=12, pady=(0, 8))

        month_row = ctk.CTkFrame(parent, fg_color="transparent")
        month_row.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(month_row, text="Month:", width=60, anchor="w").pack(side="left")
        self.selected_month = ctk.StringVar(value="January")
        ctk.CTkComboBox(month_row, variable=self.selected_month,
                        values=list(MONTHS.values()), width=160, state="readonly",
                        command=lambda _: self._refresh_monthly()).pack(side="left")

        table_frame = ctk.CTkFrame(parent)
        table_frame.pack(fill="both", expand=True, padx=12)
        cols = ("genre", "pct")
        self.monthly_tree = ttk.Treeview(table_frame, columns=cols,
                                          show="headings", height=8)
        self.monthly_tree.heading("genre", text="Genre")
        self.monthly_tree.heading("pct",   text="Discount %")
        self.monthly_tree.column("genre", width=200)
        self.monthly_tree.column("pct",   width=90)
        self.monthly_tree.pack(fill="both", expand=True)

        add_frame = ctk.CTkFrame(parent, fg_color="gray20", corner_radius=8)
        add_frame.pack(fill="x", padx=12, pady=8)
        ctk.CTkLabel(add_frame, text="Add genre to this month:",
                     anchor="w").pack(fill="x", padx=10, pady=(8, 4))
        add_row = ctk.CTkFrame(add_frame, fg_color="transparent")
        add_row.pack(fill="x", padx=10, pady=(0, 10))
        self.new_month_genre_entry = GenreEntry(add_row, width=140)
        self.new_month_genre_entry.pack(side="left", padx=(0, 6))
        self.new_month_pct_var = ctk.StringVar(value="25")
        ctk.CTkEntry(add_row, textvariable=self.new_month_pct_var,
                     width=50).pack(side="left", padx=(0, 4))
        ctk.CTkLabel(add_row, text="%").pack(side="left", padx=(0, 8))
        ctk.CTkButton(add_row, text="Add", width=70,
                      fg_color="#2a9d8f", hover_color="#21867a",
                      command=self._add_monthly_genre).pack(side="left", padx=(0, 8))
        ctk.CTkButton(add_row, text="Remove Selected", width=130,
                      fg_color="#e63946", hover_color="#c1121f",
                      command=self._remove_monthly_genre).pack(side="left")

        self._refresh_monthly()

    def _refresh_monthly(self):
        month_name = self.selected_month.get()
        month_num = [k for k, v in MONTHS.items() if v == month_name]
        if not month_num:
            return
        month_num = month_num[0]
        rows = get_monthly_discounts_for_month(month_num)
        for item in self.monthly_tree.get_children():
            self.monthly_tree.delete(item)
        for mid, genre, pct in rows:
            self.monthly_tree.insert("", "end", iid=str(mid),
                                     values=(genre, f"{pct:.0f}%"))

    def _add_monthly_genre(self):
        month_name = self.selected_month.get()
        month_num = [k for k, v in MONTHS.items() if v == month_name]
        if not month_num:
            return
        month_num = month_num[0]
        genre = self.new_month_genre_entry.get()
        if not genre:
            messagebox.showwarning("Missing", "Enter a genre name.", parent=self)
            return
        try:
            pct = float(self.new_month_pct_var.get().strip())
        except ValueError:
            messagebox.showwarning("Invalid", "Enter a valid percentage.", parent=self)
            return
        ensure_genre(genre)
        add_monthly_discount(month_num, genre, pct)
        self.new_month_genre_entry.set("")
        self.new_month_pct_var.set("25")
        self._refresh_monthly()

    def _remove_monthly_genre(self):
        sel = self.monthly_tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Select a genre to remove.", parent=self)
            return
        if messagebox.askyesno("Confirm", "Remove this genre from the monthly discount?",
                               parent=self):
            delete_monthly_discount(int(sel[0]))
            self._refresh_monthly()


# ── Settings Window ───────────────────────────────────────────────────────────
class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Settings")
        self.geometry("560x560")
        self.resizable(False, False)
        self.grab_set()
        self._build_ui()

    def _build_ui(self):
        # ── Invoice migration ──────────────────────────────────────────────
        ctk.CTkLabel(self, text="Migration Settings",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(16, 2))
        ctk.CTkLabel(self,
                     text="Set the last invoice number used in BookTrakker.\n"
                          "New invoices continue from this number.",
                     text_color="gray", justify="center").pack()
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=8)
        ctk.CTkLabel(row, text="Last Invoice #:", width=130, anchor="w").pack(side="left")
        self.inv_var = ctk.StringVar(value=get_setting("last_invoice") or "0")
        ctk.CTkEntry(row, textvariable=self.inv_var, width=120).pack(side="left")
        ctk.CTkButton(self, text="Save Invoice Setting", command=self._save_invoice,
                      fg_color="#2a9d8f", hover_color="#21867a").pack(pady=(0, 12))

        ctk.CTkFrame(self, height=1, fg_color="gray30").pack(fill="x", padx=20, pady=(0, 12))

        # ── Genre Manager ──────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Genre Manager",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(0, 4))
        ctk.CTkLabel(self,
                     text="Renaming a genre updates all inventory, discounts, and sales.",
                     text_color="gray").pack(pady=(0, 6))

        list_frame = ctk.CTkFrame(self)
        list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 8))
        self.genre_listbox = tk.Listbox(
            list_frame,
            bg="#2b2b2b", fg="white",
            selectbackground="#1f538d", selectforeground="white",
            activestyle="none", highlightthickness=0, borderwidth=0,
            font=("Segoe UI", 11), height=10,
        )
        sb = tk.Scrollbar(list_frame, orient="vertical",
                          command=self.genre_listbox.yview)
        self.genre_listbox.configure(yscrollcommand=sb.set)
        self.genre_listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._refresh_genre_list()

        # Add / Rename / Delete controls
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=20, pady=(0, 8))

        self.genre_edit_var = ctk.StringVar()
        ctk.CTkEntry(ctrl, textvariable=self.genre_edit_var,
                     width=220, placeholder_text="Genre name…").pack(side="left", padx=(0, 8))

        ctk.CTkButton(ctrl, text="Add", width=70,
                      fg_color="#2a9d8f", hover_color="#21867a",
                      command=self._add_genre).pack(side="left", padx=(0, 6))
        ctk.CTkButton(ctrl, text="Rename Selected", width=130,
                      command=self._rename_genre).pack(side="left", padx=(0, 6))
        ctk.CTkButton(ctrl, text="Delete", width=80,
                      fg_color="#e63946", hover_color="#c1121f",
                      command=self._delete_genre).pack(side="left")

    def _refresh_genre_list(self):
        self.genre_listbox.delete(0, "end")
        for g in get_all_genres():
            self.genre_listbox.insert("end", f"  {g}")

    def _selected_genre(self):
        sel = self.genre_listbox.curselection()
        if not sel:
            return None
        return self.genre_listbox.get(sel[0]).strip()

    def _add_genre(self):
        name = self.genre_edit_var.get().strip()
        if not name:
            messagebox.showwarning("Missing", "Enter a genre name.", parent=self)
            return
        ensure_genre(name)
        self.genre_edit_var.set("")
        self._refresh_genre_list()

    def _rename_genre(self):
        old = self._selected_genre()
        if not old:
            messagebox.showinfo("No Selection", "Select a genre to rename.", parent=self)
            return
        new = self.genre_edit_var.get().strip()
        if not new:
            messagebox.showwarning("Missing",
                                   "Type the new name in the field first.", parent=self)
            return
        if messagebox.askyesno(
                "Confirm Rename",
                f"Rename \"{old}\" → \"{new}\"?\n\n"
                f"This will update all inventory, discounts, and past sales.",
                parent=self):
            rename_genre(old, new)
            self.genre_edit_var.set("")
            self._refresh_genre_list()

    def _delete_genre(self):
        name = self._selected_genre()
        if not name:
            messagebox.showinfo("No Selection", "Select a genre to delete.", parent=self)
            return
        if messagebox.askyesno(
                "Confirm Delete",
                f"Remove \"{name}\" from the genre list?\n\n"
                f"Existing inventory with this genre is not affected.",
                parent=self):
            delete_genre(name)
            self._refresh_genre_list()

    def _save_invoice(self):
        try:
            val = int(self.inv_var.get().strip())
        except ValueError:
            messagebox.showwarning("Invalid", "Please enter a whole number.", parent=self)
            return
        set_setting("last_invoice", str(val))
        messagebox.showinfo("Saved",
                            f"Invoice numbering will continue from {val + 1}.",
                            parent=self)


# ── Inventory Tab ─────────────────────────────────────────────────────────────
class InventoryFrame(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._build_ui()
        self.refresh_table()

    def _build_ui(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", pady=(0, 8))
        ctk.CTkButton(top, text="+ Add Book", width=110, fg_color="#2a9d8f",
                      hover_color="#21867a", command=self._open_add).pack(side="left")
        ctk.CTkLabel(top, text="Search:").pack(side="left", padx=(20, 6))
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_table())
        ctk.CTkEntry(top, textvariable=self.search_var,
                     placeholder_text="Search inventory…", width=280).pack(side="left")
        ctk.CTkLabel(top, text="  in:").pack(side="left")
        self.filter_var = ctk.StringVar(value="All")
        ctk.CTkComboBox(top, variable=self.filter_var,
                        values=["All", "Title", "Author", "Genre", "ISBN"],
                        width=120, state="readonly",
                        command=lambda _: self.refresh_table()).pack(side="left", padx=8)
        self.count_label = ctk.CTkLabel(top, text="", text_color="gray")
        self.count_label.pack(side="right")

        table_frame = ctk.CTkFrame(self)
        table_frame.pack(fill="both", expand=True)
        columns = ("invoice_no", "title", "author", "genre", "price", "location")
        self.tree = ttk.Treeview(table_frame, columns=columns,
                                  show="headings", selectmode="browse")
        for col, heading, width in [
            ("invoice_no", "Invoice #", 80), ("title", "Title", 300),
            ("author", "Author", 180), ("genre", "Genre", 130),
            ("price", "Price", 75), ("location", "Location", 110)]:
            self.tree.heading(col, text=heading,
                              command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=width, minwidth=40)
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._on_double_click)

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(bottom, text="✏  Edit Selected", width=140,
                      command=self._open_edit).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bottom, text="🗑  Delete Selected", width=150,
                      fg_color="#e63946", hover_color="#c1121f",
                      command=self._delete_selected).pack(side="left")
        self._sort_col = "invoice_no"
        self._sort_rev = True

    def refresh_table(self):
        rows = get_all_books(self.search_var.get().strip(), self.filter_var.get())
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in rows:
            inv, title, author, genre, price, loc, isbn, db_id = row
            price_str = f"${price:.2f}" if price is not None else ""
            self.tree.insert("", "end", iid=str(db_id),
                             values=(inv, title, author or "", genre or "",
                                     price_str, loc or ""))
        self.count_label.configure(
            text=f"{len(rows)} book{'s' if len(rows) != 1 else ''}")

    def _sort_by(self, col):
        rows = get_all_books(self.search_var.get().strip(), self.filter_var.get())
        col_map = {"invoice_no": 0, "title": 1, "author": 2,
                   "genre": 3, "price": 4, "location": 5}
        idx = col_map.get(col, 0)
        reverse = (self._sort_col == col) and not self._sort_rev
        self._sort_col, self._sort_rev = col, reverse
        rows.sort(key=lambda r: (r[idx] or ""), reverse=reverse)
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in rows:
            inv, title, author, genre, price, loc, isbn, db_id = row
            price_str = f"${price:.2f}" if price is not None else ""
            self.tree.insert("", "end", iid=str(db_id),
                             values=(inv, title, author or "", genre or "",
                                     price_str, loc or ""))

    def _get_selected_book(self):
        sel = self.tree.selection()
        if not sel:
            return None
        db_id = int(sel[0])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""SELECT id,invoice_no,isbn,title,author,genre,price,location
                     FROM inventory WHERE id=?""", (db_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return {"id": row[0], "invoice_no": row[1], "isbn": row[2], "title": row[3],
                "author": row[4], "genre": row[5], "price": row[6], "location": row[7]}

    def _open_add(self):
        BookFormWindow(self, on_save=self.refresh_table)

    def _open_edit(self):
        book = self._get_selected_book()
        if not book:
            messagebox.showinfo("No Selection", "Please select a book to edit.")
            return
        BookFormWindow(self, on_save=self.refresh_table, book=book)

    def _on_double_click(self, _):
        book = self._get_selected_book()
        if book:
            BookFormWindow(self, on_save=self.refresh_table, book=book)

    def _delete_selected(self):
        book = self._get_selected_book()
        if not book:
            messagebox.showinfo("No Selection", "Please select a book to delete.")
            return
        if messagebox.askyesno(
                "Confirm Delete",
                f"Delete \"{book['title']}\" (Invoice #{book['invoice_no']})?\n\nThis cannot be undone."):
            delete_book(book["id"])
            self.refresh_table()


# ── Do Not Take Tab ──────────────────────────────────────────────────────────
class DoNotTakeFrame(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._editing_id = None
        self._build_ui()
        self.refresh_table()

    def _build_ui(self):
        # ── Check panel ───────────────────────────────────────────────────
        check_frame = ctk.CTkFrame(self, fg_color="gray20", corner_radius=8)
        check_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(check_frame, text="🔍  Check a Donation",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     anchor="w").pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(check_frame,
                     text="Type or scan a book's details below and press Check.",
                     text_color="gray", anchor="w").pack(fill="x", padx=14, pady=(0, 8))

        fields_row = ctk.CTkFrame(check_frame, fg_color="transparent")
        fields_row.pack(fill="x", padx=14, pady=(0, 4))

        for label, attr in [("Title", "chk_title"), ("Author", "chk_author")]:
            ctk.CTkLabel(fields_row, text=f"{label}:", width=55, anchor="w").pack(side="left")
            var = ctk.StringVar()
            setattr(self, attr, var)
            entry = ctk.CTkEntry(fields_row, textvariable=var, width=220,
                                 placeholder_text=f"Enter {label.lower()}…")
            entry.pack(side="left", padx=(0, 16))
            entry.bind("<Return>", lambda e: self._check())

        ctk.CTkButton(fields_row, text="Check", width=90,
                      fg_color="#1f538d", hover_color="#1a4578",
                      command=self._check).pack(side="left")
        ctk.CTkButton(fields_row, text="Clear", width=70,
                      fg_color="gray30", hover_color="gray40",
                      command=self._clear_check).pack(side="left", padx=(6, 0))

        self.result_label = ctk.CTkLabel(check_frame, text="",
                                          font=ctk.CTkFont(size=13, weight="bold"),
                                          wraplength=700, justify="left")
        self.result_label.pack(fill="x", padx=14, pady=(4, 10))

        # ── List panel ────────────────────────────────────────────────────
        list_top = ctk.CTkFrame(self, fg_color="transparent")
        list_top.pack(fill="x", pady=(0, 6))

        ctk.CTkButton(list_top, text="+ Add Entry", width=110,
                      fg_color="#2a9d8f", hover_color="#21867a",
                      command=self._open_add).pack(side="left")

        ctk.CTkLabel(list_top, text="Search:").pack(side="left", padx=(20, 6))
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_table())
        ctk.CTkEntry(list_top, textvariable=self.search_var,
                     placeholder_text="Search list…", width=240).pack(side="left")

        ctk.CTkLabel(list_top, text="  Show:").pack(side="left")
        self.filter_var = ctk.StringVar(value="All")
        ctk.CTkComboBox(list_top, variable=self.filter_var,
                        values=["All", "Author", "Title", "Category"],
                        width=120, state="readonly",
                        command=lambda _: self.refresh_table()).pack(side="left", padx=8)

        self.count_label = ctk.CTkLabel(list_top, text="", text_color="gray")
        self.count_label.pack(side="right")

        table_frame = ctk.CTkFrame(self)
        table_frame.pack(fill="both", expand=True)
        cols = ("type", "value", "status", "note")
        self.tree = ttk.Treeview(table_frame, columns=cols,
                                  show="headings", selectmode="browse")
        self.tree.heading("type",   text="Type")
        self.tree.heading("value",  text="Author / Title / Category")
        self.tree.heading("status", text="Status")
        self.tree.heading("note",   text="Notes / Keep Rules")
        self.tree.column("type",   width=80,  minwidth=60)
        self.tree.column("value",  width=230, minwidth=100)
        self.tree.column("status", width=110, minwidth=80)
        self.tree.column("note",   width=290, minwidth=80)
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._on_double_click)

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", pady=(6, 0))
        ctk.CTkButton(bottom, text="✏  Edit Selected", width=140,
                      command=self._open_edit).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bottom, text="🗑  Delete Selected", width=150,
                      fg_color="#e63946", hover_color="#c1121f",
                      command=self._delete_selected).pack(side="left")

    # ── Check logic ───────────────────────────────────────────────────────
    def _check(self):
        title  = self.chk_title.get().strip()
        author = self.chk_author.get().strip()
        if not title and not author:
            self.result_label.configure(
                text="Enter a title or author to check.", text_color="gray")
            return
        matches = check_do_not_take(title=title, author=author)
        if matches:
            lines_out = []
            has_hard_dnt = False
            for _, mtype, mval, mnote, is_dnt in matches:
                if is_dnt:
                    has_hard_dnt = True
                    line = f"\u26d4  DO NOT TAKE \u2014 {mtype.upper()}: {mval}"
                else:
                    line = f"\u26a0\ufe0f  CONDITIONAL \u2014 {mtype.upper()}: {mval}"
                if mnote:
                    line += f"  \u2192  {mnote}"
                lines_out.append(line)
            color = "#e63946" if has_hard_dnt else "#e9c46a"
            self.result_label.configure(
                text="\n".join(lines_out), text_color=color)
        else:
            self.result_label.configure(
                text="\u2713  Not on the do-not-take list.", text_color="#2a9d8f")

    def _clear_check(self):
        self.chk_title.set("")
        self.chk_author.set("")
        self.result_label.configure(text="")

    # ── Table ─────────────────────────────────────────────────────────────
    def refresh_table(self):
        rows = get_do_not_take(self.search_var.get().strip(), self.filter_var.get())
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in rows:
            rid, rtype, rvalue, rnote, is_dnt = row
            status = "Do Not Take" if is_dnt else "Conditional"
            self.tree.insert("", "end", iid=str(rid),
                             values=(rtype.capitalize(), rvalue, status, rnote or ""))
        self.count_label.configure(
            text=f"{len(rows)} entr{'ies' if len(rows) != 1 else 'y'}")

    def _get_selected(self):
        sel = self.tree.selection()
        if not sel:
            return None
        rid = int(sel[0])
        rows = get_do_not_take()
        for row in rows:
            if row[0] == rid:
                return {"id": row[0], "type": row[1], "value": row[2],
                        "note": row[3] or "", "do_not_take": bool(row[4])}
        return None

    def _open_add(self):
        DoNotTakeFormWindow(self, on_save=self.refresh_table)

    def _open_edit(self):
        entry = self._get_selected()
        if not entry:
            messagebox.showinfo("No Selection", "Please select an entry to edit.")
            return
        DoNotTakeFormWindow(self, on_save=self.refresh_table, entry=entry)

    def _on_double_click(self, _):
        entry = self._get_selected()
        if entry:
            DoNotTakeFormWindow(self, on_save=self.refresh_table, entry=entry)

    def _delete_selected(self):
        entry = self._get_selected()
        if not entry:
            messagebox.showinfo("No Selection", "Please select an entry to delete.")
            return
        label = f"{entry['type'].capitalize()}: {entry['value']}"
        if messagebox.askyesno("Confirm Delete",
                               f"Remove \"{label}\" from the list?"):
            delete_do_not_take(entry["id"])
            self.refresh_table()


# ── Do Not Take Form Window ───────────────────────────────────────────────────
class DoNotTakeFormWindow(ctk.CTkToplevel):
    def __init__(self, parent, on_save, entry=None):
        super().__init__(parent)
        self.on_save = on_save
        self.entry = entry
        self.title("Edit Entry" if entry else "Add Entry")
        self.geometry("460x290")
        self.resizable(False, False)
        self.grab_set()
        self._build_ui()
        if entry:
            self._populate(entry)

    def _build_ui(self):
        pad = {"padx": 24, "pady": 8}

        type_row = ctk.CTkFrame(self, fg_color="transparent")
        type_row.pack(fill="x", **pad)
        ctk.CTkLabel(type_row, text="Type *", width=80, anchor="w").pack(side="left")
        self.type_var = ctk.StringVar(value="author")
        ctk.CTkComboBox(type_row, variable=self.type_var,
                        values=["author", "title", "category"],
                        width=140, state="readonly").pack(side="left")

        dnt_row = ctk.CTkFrame(self, fg_color="transparent")
        dnt_row.pack(fill="x", **pad)
        ctk.CTkLabel(dnt_row, text="Status *", width=80, anchor="w").pack(side="left")
        self.dnt_var = ctk.StringVar(value="Do Not Take")
        ctk.CTkComboBox(dnt_row, variable=self.dnt_var,
                        values=["Do Not Take", "Conditional"],
                        width=160, state="readonly").pack(side="left")
        ctk.CTkLabel(dnt_row, text="  (Conditional = keep rules apply)",
                     text_color="gray").pack(side="left")

        value_row = ctk.CTkFrame(self, fg_color="transparent")
        value_row.pack(fill="x", **pad)
        ctk.CTkLabel(value_row, text="Name *", width=80, anchor="w").pack(side="left")
        self.value_var = ctk.StringVar()
        self.value_entry = ctk.CTkEntry(value_row, textvariable=self.value_var,
                                         width=300, placeholder_text="Author or title name")
        self.value_entry.pack(side="left")

        note_row = ctk.CTkFrame(self, fg_color="transparent")
        note_row.pack(fill="x", **pad)
        ctk.CTkLabel(note_row, text="Notes", width=80, anchor="w").pack(side="left")
        self.note_var = ctk.StringVar()
        ctk.CTkEntry(note_row, textvariable=self.note_var, width=300,
                     placeholder_text="e.g. except hardcovers").pack(side="left")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=24, pady=16)
        ctk.CTkButton(btn_frame, text="Save", command=self._save,
                      fg_color="#2a9d8f", hover_color="#21867a").pack(side="left", padx=(0, 10))
        ctk.CTkButton(btn_frame, text="Cancel", command=self.destroy,
                      fg_color="gray30", hover_color="gray40").pack(side="left")
        self.after(100, self.value_entry.focus_set)

    def _populate(self, entry):
        self.type_var.set(entry["type"])
        self.dnt_var.set("Do Not Take" if entry.get("do_not_take", True) else "Conditional")
        self.value_var.set(entry["value"])
        self.note_var.set(entry["note"])

    def _save(self):
        value = self.value_var.get().strip()
        if not value:
            highlight_required(self.value_entry, False)
            messagebox.showwarning("Missing", "Please enter a name.", parent=self)
            return
        highlight_required(self.value_entry, True)
        is_dnt = self.dnt_var.get() == "Do Not Take"
        if self.entry:
            update_do_not_take(self.entry["id"], self.type_var.get(),
                               value, self.note_var.get(), is_dnt)
        else:
            save_do_not_take(self.type_var.get(), value, self.note_var.get(), is_dnt)
        self.on_save()
        self.destroy()


# ── Wants Dialogs ─────────────────────────────────────────────────────────────
class AddWantDialog(ctk.CTkToplevel):
    def __init__(self, parent, customer_id, on_save):
        super().__init__(parent)
        self.title("Add Want")
        self.resizable(False, False)
        self.grab_set()
        self._customer_id = customer_id
        self._on_save = on_save
        pad = {"padx": 20, "pady": 6}

        ctk.CTkLabel(self, text="Add Book to Want List",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(**pad)

        for label, attr, placeholder in [
            ("Title",          "title_var",  "Book title"),
            ("Author (Last, First)", "author_var", "e.g. King, Stephen"),
            ("ISBN",           "isbn_var",   "Optional"),
            ("Notes",          "notes_var",  "Any details…"),
        ]:
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", **pad)
            ctk.CTkLabel(row, text=label, width=140, anchor="w").pack(side="left")
            var = ctk.StringVar()
            setattr(self, attr, var)
            ctk.CTkEntry(row, textvariable=var, width=280,
                         placeholder_text=placeholder).pack(side="left")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=16)
        ctk.CTkButton(btn_row, text="Add Want", fg_color="#2a9d8f",
                      hover_color="#21867a", command=self._save).pack(side="left", padx=(0, 10))
        ctk.CTkButton(btn_row, text="Cancel", fg_color="gray30",
                      hover_color="gray40", command=self.destroy).pack(side="left")

    def _save(self):
        title  = self.title_var.get().strip()
        author = self.author_var.get().strip()
        isbn   = self.isbn_var.get().strip()
        notes  = self.notes_var.get().strip()
        if not title and not author and not isbn:
            messagebox.showwarning("Missing Info",
                                   "Please enter at least a title, author, or ISBN.",
                                   parent=self)
            return
        add_want(self._customer_id, title, author, isbn, notes)
        self._on_save()
        self.destroy()


class WantsDialog(ctk.CTkToplevel):
    def __init__(self, parent, customer):
        super().__init__(parent)
        self.title(f"Want List — {customer['name']}")
        self.geometry("640x420")
        self.grab_set()
        self._customer = customer
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(top, text=f"Want list for {self._customer['name']}",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkButton(top, text="+ Add Want", width=110, fg_color="#2a9d8f",
                      hover_color="#21867a",
                      command=self._open_add).pack(side="right")

        table_frame = ctk.CTkFrame(self)
        table_frame.pack(fill="both", expand=True, padx=16, pady=10)
        cols = ("title", "author", "isbn", "notes", "date")
        self.tree = ttk.Treeview(table_frame, columns=cols,
                                  show="headings", selectmode="browse")
        for col, heading, width in [
            ("title",  "Title",  200), ("author", "Author", 140),
            ("isbn",   "ISBN",    90), ("notes",  "Notes",  130),
            ("date",   "Added",   80)]:
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, minwidth=40)
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkButton(bottom, text="🗑  Remove Selected", fg_color="#e63946",
                      hover_color="#c1121f", width=160,
                      command=self._remove_selected).pack(side="left")

    def _refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in get_wants_for_customer(self._customer["id"]):
            wid, title, author, isbn, notes, date_added = row
            self.tree.insert("", "end", iid=str(wid),
                             values=(title or "", author or "", isbn or "",
                                     notes or "", date_added or ""))

    def _open_add(self):
        AddWantDialog(self, self._customer["id"], on_save=self._refresh)

    def _remove_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        if messagebox.askyesno("Remove Want", "Remove this want from the list?",
                                parent=self):
            delete_want(int(sel[0]))
            self._refresh()


# ── Customers Tab ─────────────────────────────────────────────────────────────
class CustomersFrame(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._build_ui()
        self.refresh_table()

    def _build_ui(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", pady=(0, 8))
        ctk.CTkButton(top, text="+ Add Customer", width=140, fg_color="#2a9d8f",
                      hover_color="#21867a",
                      command=self._open_add).pack(side="left")
        ctk.CTkLabel(top, text="Search:").pack(side="left", padx=(20, 6))
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_table())
        ctk.CTkEntry(top, textvariable=self.search_var,
                     placeholder_text="Name, phone, or email…",
                     width=260).pack(side="left")
        self.count_label = ctk.CTkLabel(top, text="", text_color="gray")
        self.count_label.pack(side="right")

        table_frame = ctk.CTkFrame(self)
        table_frame.pack(fill="both", expand=True)
        cols = ("name", "phone", "email", "deros", "contact",
                "handle", "reg_credit", "coll_credit")
        self.tree = ttk.Treeview(table_frame, columns=cols,
                                  show="headings", selectmode="browse")
        for col, heading, width in [
            ("name", "Name", 180), ("phone", "Phone", 110),
            ("email", "Email", 170), ("deros", "DEROS", 90),
            ("contact", "Pref. Contact", 100), ("handle", "Handle", 120),
            ("reg_credit", "Reg. Credit", 85), ("coll_credit", "Coll. Credit", 85)]:
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, minwidth=40)
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._on_double_click)

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(bottom, text="✏  Edit Selected", width=140,
                      command=self._open_edit).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bottom, text="💳  Store Credit", width=140,
                      fg_color="#1f538d", hover_color="#1a4578",
                      command=self._open_credit).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bottom, text="📋  Wants", width=110,
                      fg_color="#6a4c93", hover_color="#553d78",
                      command=self._open_wants).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bottom, text="🗑  Delete Selected", width=150,
                      fg_color="#e63946", hover_color="#c1121f",
                      command=self._delete_selected).pack(side="left")

    def refresh_table(self):
        rows = get_all_customers(self.search_var.get().strip())
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in rows:
            cid, name, phone, email, deros, contact, handle, reg_credit, coll_credit = row
            deros_disp = deros or ""
            if deros_disp and "-" in deros_disp:
                parts = deros_disp.split("-")
                if len(parts) == 2:
                    try:
                        deros_disp = f"{MONTH_NAMES[int(parts[1])-1]} {parts[0]}"
                    except Exception:
                        pass
            self.tree.insert("", "end", iid=str(cid),
                             values=(name, phone or "", email or "", deros_disp,
                                     contact or "", handle or "",
                                     f"${reg_credit:.2f}" if reg_credit else "$0.00",
                                     f"${coll_credit:.2f}" if coll_credit else "$0.00"))
        self.count_label.configure(
            text=f"{len(rows)} customer{'s' if len(rows) != 1 else ''}")

    def _get_selected(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return get_customer(int(sel[0]))

    def _open_add(self):
        CustomerFormWindow(self, on_save=self.refresh_table)

    def _open_edit(self):
        c = self._get_selected()
        if not c:
            messagebox.showinfo("No Selection", "Please select a customer to edit.")
            return
        CustomerFormWindow(self, on_save=self.refresh_table, customer=c)

    def _on_double_click(self, _):
        c = self._get_selected()
        if c:
            CustomerFormWindow(self, on_save=self.refresh_table, customer=c)

    def _open_credit(self):
        c = self._get_selected()
        if not c:
            messagebox.showinfo("No Selection", "Please select a customer.")
            return
        CreditWindow(self, c, on_save=self.refresh_table)

    def _open_wants(self):
        c = self._get_selected()
        if not c:
            messagebox.showinfo("No Selection", "Please select a customer.")
            return
        WantsDialog(self, c)

    def _delete_selected(self):
        c = self._get_selected()
        if not c:
            messagebox.showinfo("No Selection", "Please select a customer to delete.")
            return
        if messagebox.askyesno(
                "Confirm Delete",
                f"Delete \"{c['name']}\"?\nThis will also delete their credit history."):
            delete_customer(c["id"])
            self.refresh_table()


# ── Main Application ──────────────────────────────────────────────────────────
class BookstoreApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("📚 BaseBooks  v1.4")
        self.geometry("1200x740")
        self.minsize(900, 560)
        self._build_ui()

    def _build_ui(self):
        top = ctk.CTkFrame(self, height=56, corner_radius=0)
        top.pack(fill="x", side="top")
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="📚  BaseBooks",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(side="left", padx=20)
        ctk.CTkButton(top, text="⚙  Settings", width=110, fg_color="gray30",
                      hover_color="gray40",
                      command=self._open_settings).pack(side="right", padx=10, pady=10)

        # ── Custom tab bar (plain tk.Button — no canvas, no CTk overhead) ──
        TAB_BG       = "#1a1a1a"
        TAB_ACTIVE   = "#2563eb"
        TAB_FG       = "#808080"
        TAB_FG_ACT   = "#ffffff"
        TAB_FONT     = ("Segoe UI", 11)

        outer = tk.Frame(self, bg="#1a1a1a")
        outer.pack(fill="both", expand=True, padx=16, pady=16)

        bar = tk.Frame(outer, bg="#1a1a1a", height=36)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        content = ctk.CTkFrame(outer, fg_color="gray17", corner_radius=6)
        content.pack(fill="both", expand=True, pady=(4, 0))

        self._tab_frames  = {}
        self._tab_buttons = {}
        self._active_tab  = None

        def _switch(name):
            if self._active_tab == name:
                return
            if self._active_tab and self._active_tab in self._tab_frames:
                self._tab_frames[self._active_tab].pack_forget()
                self._tab_buttons[self._active_tab].config(
                    bg=TAB_BG, fg=TAB_FG, relief="flat", bd=0)
            self._active_tab = name
            self._tab_frames[name].pack(fill="both", expand=True, padx=8, pady=8)
            self._tab_buttons[name].config(
                bg=TAB_ACTIVE, fg=TAB_FG_ACT, relief="ridge", bd=2)

        tab_defs = [
            ("📦  Inventory",    InventoryFrame),
            ("👤  Customers",    CustomersFrame),
            ("🛒  Checkout",     CheckoutFrame),
            ("🏷  Discounts",    DiscountsFrame),
            ("⭐  Special Sales", SpecialSalesFrame),
            ("🚫  Do Not Take",  DoNotTakeFrame),
        ]

        for name, FrameClass in tab_defs:
            frame = FrameClass(content)
            self._tab_frames[name] = frame

            btn = tk.Button(bar, text=name, font=TAB_FONT,
                            bg=TAB_BG, fg=TAB_FG,
                            activebackground=TAB_ACTIVE, activeforeground=TAB_FG_ACT,
                            bd=0, relief="flat", padx=14, pady=6, cursor="hand2",
                            command=lambda n=name: _switch(n))
            btn.pack(side="left", padx=(0, 2))
            self._tab_buttons[name] = btn

        _switch("📦  Inventory")

    def _open_settings(self):
        SettingsWindow(self)


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    app = BookstoreApp()
    app.mainloop()
