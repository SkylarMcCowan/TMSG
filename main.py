import json
import queue
import re
import threading
import tkinter as tk
from html.parser import HTMLParser
from tkinter import ttk, messagebox
import urllib.error
import urllib.parse
import urllib.request

# Multiple TPB proxy endpoints; searches merge results across all working sources.
API_ENDPOINTS = [
    {"name": "apibay.org", "url": "https://apibay.org/q.php?q={query}&cat={category}"},
    {
        "name": "pirateproxy.live",
        "url": "https://pirateproxy.live/apibay/q.php?q={query}&cat={category}",
    },
    {"name": "apibay.sbs", "url": "https://apibay.sbs/q.php?q={query}&cat={category}"},
]

# HTML search endpoints, starting with the primary TPB domain.
HTML_ENDPOINTS = [
    {"name": "thepiratebay.org", "url": "https://thepiratebay.org/search/{query}/1/99/{cat}"},
    {"name": "thepiratebay0.org", "url": "https://thepiratebay0.org/search/{query}/1/99/{cat}"},
    {"name": "tpb.party", "url": "https://tpb.party/search/{query}/1/99/{cat}"},
]

# TPB category sets to query (we try each until we get results).
CATEGORY_SETS = {
    "movies_hd": ["207", "201", "200"],  # HD Movies, then fallback to Movies/Video
    "shows_hd": ["208", "205", "200"],   # HD TV, fallback to TV/Video
    "all_video": ["200", "0"],            # Broadest search
    "music": ["101", "100", "0"],        # Music, then fallback to Audio/all categories
    "books": ["601", "0"],                # Books, fallback to all categories
}

TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.demonii.com:1337/announce",
    "udp://tracker.coppersurfer.tk:6969/announce",
    "udp://tracker.leechers-paradise.org:6969/announce",
]


def parse_size_bytes(text: str) -> int:
    """Extract size in bytes from TPB detDesc text."""
    match = re.search(r"Size ([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)", text)
    if not match:
        return 0
    value = float(match.group(1))
    unit = match.group(2).lower()
    scale = {
        "b": 1,
        "kib": 1024,
        "kb": 1024,
        "mib": 1024 ** 2,
        "mb": 1024 ** 2,
        "gib": 1024 ** 3,
        "gb": 1024 ** 3,
        "tib": 1024 ** 4,
        "tb": 1024 ** 4,
    }.get(unit, 1)
    return int(value * scale)


def parse_btih_from_magnet(magnet: str) -> str | None:
    if not magnet.startswith("magnet:?"):
        return None
    parsed = urllib.parse.urlparse(magnet)
    qs = urllib.parse.parse_qs(parsed.query)
    xt_values = qs.get("xt") or []
    for xt in xt_values:
        if xt.startswith("urn:btih:"):
            return xt.split(":", 2)[-1]
    return None


def merge_unique_results(rows):
    merged = []
    seen_hashes = set()
    for row in rows:
        info_hash = row.get("info_hash")
        if not info_hash:
            continue
        key = str(info_hash).lower()
        if key in seen_hashes:
            continue
        seen_hashes.add(key)
        merged.append(row)
    return merged


def summarize_health(health, max_names: int = 2) -> str:
    if not health:
        return "No endpoints checked."
    ok = [item for item in health if item["status"] == "ok"]
    empty = [item for item in health if item["status"] == "empty"]
    failed = [item for item in health if item["status"] == "failed"]

    parts = []
    if ok:
        ok_text = ", ".join(f"{item['name']}:{item['count']}" for item in ok[:max_names])
        if len(ok) > max_names:
            ok_text += f", +{len(ok) - max_names} more"
        parts.append(f"ok {ok_text}")
    if empty:
        empty_text = ", ".join(item["name"] for item in empty[:max_names])
        if len(empty) > max_names:
            empty_text += f", +{len(empty) - max_names} more"
        parts.append(f"empty {empty_text}")
    if failed:
        failed_text = ", ".join(item["name"] for item in failed[:max_names])
        if len(failed) > max_names:
            failed_text += f", +{len(failed) - max_names} more"
        parts.append(f"failed {failed_text}")
    return "; ".join(parts)


class TPBHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self._reset_row()

    def _reset_row(self):
        self.in_tr = False
        self.in_det_name = False
        self.in_title_anchor = False
        self.in_det_desc = False
        self.in_align_right = False
        self.align_right_values = []
        self.current = {"name": None, "magnet": None, "size": 0}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.in_tr = True
            self.align_right_values = []
            self.current = {"name": None, "magnet": None, "size": 0}
            return
        if not self.in_tr:
            return
        if tag == "div" and attrs.get("class") == "detName":
            self.in_det_name = True
        if tag == "font" and attrs.get("class") == "detDesc":
            self.in_det_desc = True
        if tag == "a":
            href = attrs.get("href", "")
            if href.startswith("magnet:?xt="):
                self.current["magnet"] = href
            elif self.in_det_name:
                self.in_title_anchor = True
        if tag == "td" and attrs.get("align") == "right":
            self.in_align_right = True

    def handle_endtag(self, tag):
        if tag == "tr" and self.in_tr:
            info_hash = parse_btih_from_magnet(self.current.get("magnet") or "")
            if self.current.get("name") and info_hash:
                seeders = int(self.align_right_values[0]) if len(self.align_right_values) > 0 else 0
                leechers = int(self.align_right_values[1]) if len(self.align_right_values) > 1 else 0
                self.rows.append(
                    {
                        "name": self.current.get("name"),
                        "info_hash": info_hash,
                        "seeders": seeders,
                        "leechers": leechers,
                        "size": self.current.get("size", 0),
                    }
                )
            self._reset_row()
        if tag == "div":
            self.in_det_name = False
        if tag == "a":
            self.in_title_anchor = False
        if tag == "font":
            self.in_det_desc = False
        if tag == "td" and self.in_align_right:
            self.in_align_right = False

    def handle_data(self, data):
        if not self.in_tr:
            return
        text = data.strip()
        if not text:
            return
        if self.in_title_anchor and self.in_det_name:
            self.current["name"] = text
        if self.in_det_desc:
            size_bytes = parse_size_bytes(text)
            if size_bytes:
                self.current["size"] = size_bytes
        if self.in_align_right and text.isdigit():
            self.align_right_values.append(int(text))


def fetch_html_results(query: str, category_key: str):
    encoded_query = urllib.parse.quote(query)
    all_rows = []
    health = []
    for endpoint in HTML_ENDPOINTS:
        endpoint_rows = []
        endpoint_error = None
        for cat in CATEGORY_SETS[category_key]:
            url = endpoint["url"].format(query=encoded_query, cat=cat)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                parser = TPBHTMLParser()
                parser.feed(html)
                if parser.rows:
                    endpoint_rows.extend(parser.rows)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                endpoint_error = exc
                continue
        if endpoint_rows:
            all_rows.extend(endpoint_rows)
            health.append({"name": endpoint["name"], "status": "ok", "count": len(endpoint_rows)})
        else:
            health.append(
                {
                    "name": endpoint["name"],
                    "status": "failed" if endpoint_error else "empty",
                    "count": 0,
                }
            )
    if all_rows:
        return merge_unique_results(all_rows), health
    return [], health


def human_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def build_magnet(info_hash: str, name: str) -> str:
    # Light encoding: leave separators/colons intact; encode values only.
    xt = f"urn:btih:{info_hash}"
    dn = urllib.parse.quote(name, safe=" ")
    trackers = "&".join(f"tr={urllib.parse.quote(tr)}" for tr in TRACKERS)
    return f"magnet:?xt={xt}&dn={dn}&{trackers}"


def fetch_results(query: str, category_key: str):
    encoded_query = urllib.parse.quote(query)
    all_rows = []
    health = []
    for endpoint in API_ENDPOINTS:
        endpoint_rows = []
        endpoint_error = None
        for cat in CATEGORY_SETS[category_key]:
            url = endpoint["url"].format(query=encoded_query, category=cat)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            try:
                with urllib.request.urlopen(req, timeout=8) as resp:
                    body = resp.read().decode("utf-8", errors="ignore")
                data = json.loads(body)
                if isinstance(data, list) and data:
                    endpoint_rows.extend(data)
                # If empty, try next category/endpoint.
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                endpoint_error = exc
                continue
            except json.JSONDecodeError as exc:
                endpoint_error = exc
                continue
        if endpoint_rows:
            all_rows.extend(endpoint_rows)
            health.append({"name": endpoint["name"], "status": "ok", "count": len(endpoint_rows)})
        else:
            health.append(
                {
                    "name": endpoint["name"],
                    "status": "failed" if endpoint_error else "empty",
                    "count": 0,
                }
            )
    html_rows, html_health = fetch_html_results(query, category_key)
    health.extend(html_health)
    if html_rows:
        all_rows.extend(html_rows)
    if all_rows:
        return merge_unique_results(all_rows), health
    return [], health

# --- New: Fetch top movies/shows from TPB HTML top lists ---
def fetch_top_list(top_type: str):
    """
    Fetch top 100 movies, shows, music, or books from TPB's top lists.
    top_type: 'movies', 'shows', 'music', or 'books'
    Returns: list of dicts with keys: name, info_hash, seeders, leechers, size
    """
    # TPB top list categories: 201 = Movies, 205 = TV Shows, 101 = Music, 601 = E-books
    cat = {
        "movies": "201",
        "shows": "205",
        "music": "101",
        "books": "601",
    }.get(top_type, "201")
    all_rows = []
    health = []
    for endpoint in HTML_ENDPOINTS:
        url = endpoint["url"].replace("/search/{query}/1/99/{cat}", f"/top/{cat}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            parser = TPBHTMLParser()
            parser.feed(html)
            if parser.rows:
                all_rows.extend(parser.rows)
                health.append({"name": endpoint["name"], "status": "ok", "count": len(parser.rows)})
            else:
                health.append({"name": endpoint["name"], "status": "empty", "count": 0})
        except Exception:
            health.append({"name": endpoint["name"], "status": "failed", "count": 0})
            continue
    return merge_unique_results(all_rows), health


def sanitize_display_name(text: str) -> str:
    """Remove problematic Unicode/emoji characters for Tk Treeview compatibility."""
    # Keep ASCII and basic Latin Extended, exclude emoji and symbols
    return "".join(
        char for char in text
        if ord(char) < 0x2600  # Exclude symbols and emoji (starts at U+2600)
    )


def should_filter_by_resolution(category_key: str) -> bool:
    return category_key in {"movies_hd", "shows_hd", "all_video"}


def filter_and_sort(rows, resolution: str = "1080"):
    filtered = []
    for row in rows:
        name = row.get("name", "")
        if not name:
            continue
        lower_name = name.lower()
        if resolution == "1080" and "1080" not in lower_name:
            continue
        if resolution == "4k":
            has_4k = "2160" in lower_name or "4k" in lower_name or "uhd" in lower_name
            if not has_4k:
                continue
        info_hash = row.get("info_hash")
        if not info_hash:
            continue
        seeders = int(row.get("seeders", 0))
        leechers = int(row.get("leechers", 0))
        size = int(row.get("size", 0))
        # Sanitize display name to avoid Tk/emoji rendering crash
        display_name = sanitize_display_name(name)
        filtered.append(
            {
                "name": display_name,
                "info_hash": info_hash,
                "seeders": seeders,
                "leechers": leechers,
                "size": size,
            }
        )
    filtered.sort(key=lambda r: r["seeders"], reverse=True)
    return filtered[:100]


def create_app():
    root = tk.Tk()
    root.title("Magnet Finder")
    root.geometry("900x520")
    root.attributes("-fullscreen", True)
    root.bind("<Escape>", lambda event: root.attributes("-fullscreen", False))
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    category_options = {
        "Movie": "movies_hd",
        "TV Show": "shows_hd",
        "All Video": "all_video",
        "Music": "music",
        "Books": "books",
    }
    quality_options = {
        "1080p": "1080",
        "4K": "4k",
        "Any": "any",
    }
    top_options = {
        "Movies": "movies",
        "Shows": "shows",
        "Music": "music",
        "Books": "books",
    }

    query_var = tk.StringVar()
    category_var = tk.StringVar(value="Movie")
    status_var = tk.StringVar(value="Ready")
    magnet_var = tk.StringVar()
    resolution_var = tk.StringVar(value="1080p")

    # --- New: Top list type variable ---
    top_type_var = tk.StringVar(value="Movies")

    # Theme variables for dark/light mode
    theme_var = tk.BooleanVar(value=False)  # False=light, True=dark

    def apply_theme(is_dark: bool):
        """Apply light or dark colors to existing ttk widgets."""
        if is_dark:
            colors = {
                "bg": "#1e1e1e",
                "panel": "#252526",
                "field": "#2d2d30",
                "fg": "#f2f2f2",
                "muted": "#c8c8c8",
                "border": "#3f3f46",
                "button": "#3a6f50",
                "button_active": "#467f5e",
                "selected": "#0e639c",
                "selected_fg": "#ffffff",
            }
        else:
            colors = {
                "bg": "#f5f5f5",
                "panel": "#ffffff",
                "field": "#ffffff",
                "fg": "#111111",
                "muted": "#333333",
                "border": "#d0d0d0",
                "button": "#e6e6e6",
                "button_active": "#d8d8d8",
                "selected": "#0a64ad",
                "selected_fg": "#ffffff",
            }

        root.configure(background=colors["bg"])
        root.option_add("*Background", colors["bg"])
        root.option_add("*Foreground", colors["fg"])
        root.option_add("*Entry.Background", colors["field"])
        root.option_add("*Entry.Foreground", colors["fg"])
        root.option_add("*selectBackground", colors["selected"])
        root.option_add("*selectForeground", colors["selected_fg"])

        style.configure(".", background=colors["bg"], foreground=colors["fg"])
        style.configure("TFrame", background=colors["bg"])
        style.configure("TLabel", background=colors["bg"], foreground=colors["fg"])
        style.configure(
            "TButton",
            background=colors["button"],
            foreground=colors["fg"],
            bordercolor=colors["border"],
            focusthickness=1,
            focuscolor=colors["border"],
        )
        style.map(
            "TButton",
            background=[("active", colors["button_active"]), ("pressed", colors["button_active"])],
            foreground=[("disabled", colors["muted"])],
        )
        style.configure(
            "TEntry",
            fieldbackground=colors["field"],
            foreground=colors["fg"],
            insertcolor=colors["fg"],
            bordercolor=colors["border"],
            lightcolor=colors["border"],
            darkcolor=colors["border"],
        )
        style.configure(
            "TCombobox",
            fieldbackground=colors["field"],
            background=colors["button"],
            foreground=colors["fg"],
            arrowcolor=colors["fg"],
            bordercolor=colors["border"],
            lightcolor=colors["border"],
            darkcolor=colors["border"],
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", colors["field"])],
            foreground=[("readonly", colors["fg"])],
            selectbackground=[("readonly", colors["field"])],
            selectforeground=[("readonly", colors["fg"])],
        )
        style.configure(
            "Treeview",
            background=colors["panel"],
            fieldbackground=colors["panel"],
            foreground=colors["fg"],
            bordercolor=colors["border"],
            rowheight=24,
        )
        style.map(
            "Treeview",
            background=[("selected", colors["selected"])],
            foreground=[("selected", colors["selected_fg"])],
        )
        style.configure(
            "Treeview.Heading",
            background=colors["button"],
            foreground=colors["fg"],
            bordercolor=colors["border"],
            relief="flat",
        )
        style.map("Treeview.Heading", background=[("active", colors["button_active"])])
        style.configure(
            "Vertical.TScrollbar",
            background=colors["button"],
            troughcolor=colors["bg"],
            bordercolor=colors["border"],
            arrowcolor=colors["fg"],
        )

        try:
            theme_btn.configure(text="Light Mode" if is_dark else "Dark Mode")
        except NameError:
            pass

    def on_theme_toggle():
        """Toggle between light and dark themes."""
        theme_var.set(not theme_var.get())
        is_dark = theme_var.get()
        apply_theme(is_dark)
        status_var.set("Theme switched to" + (" dark mode" if is_dark else " light mode"))

    def selected_value(options: dict[str, str], selected_label: str) -> str:
        return options.get(selected_label, next(iter(options.values())))

    task_queue = queue.Queue()
    active_task = {"running": False}

    def set_busy(is_busy: bool):
        button_state = "disabled" if is_busy else "normal"
        combo_state = "disabled" if is_busy else "readonly"
        entry_state = "disabled" if is_busy else "normal"

        search_btn.configure(state=button_state)
        browse_btn.configure(state=button_state)
        query_entry.configure(state=entry_state)
        category_combo.configure(state=combo_state)
        quality_combo.configure(state=combo_state)
        top_combo.configure(state=combo_state)

    def populate_table(results):
        table.delete(*table.get_children())
        for idx, row in enumerate(results, start=1):
            table.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    row["name"],
                    row["seeders"],
                    row["leechers"],
                    human_size(row["size"]),
                ),
                tags=(row["info_hash"],),
            )

    def poll_task_queue():
        try:
            status, on_success, payload, error_title = task_queue.get_nowait()
        except queue.Empty:
            if active_task["running"]:
                root.after(100, poll_task_queue)
            return

        active_task["running"] = False
        set_busy(False)
        if status == "ok":
            on_success(payload)
            return

        status_var.set("Error")
        messagebox.showerror(error_title, str(payload))

    def run_background(status_text: str, worker, on_success, error_title: str):
        if active_task["running"]:
            return
        active_task["running"] = True
        set_busy(True)
        status_var.set(status_text)

        def target():
            try:
                task_queue.put(("ok", on_success, worker(), error_title))
            except Exception as exc:  # pylint: disable=broad-except
                task_queue.put(("error", on_success, exc, error_title))

        threading.Thread(target=target, daemon=True).start()
        root.after(100, poll_task_queue)

    def on_search():
        query = query_var.get().strip()
        if not query:
            messagebox.showinfo("Missing query", "Please enter a search term.")
            return

        category_key = selected_value(category_options, category_var.get())
        resolution_key = selected_value(quality_options, resolution_var.get())
        apply_resolution = should_filter_by_resolution(category_key)

        def worker():
            raw, health = fetch_results(query, category_key)
            results = filter_and_sort(
                raw, resolution=resolution_key if apply_resolution else "any"
            )
            return results, health

        def finish(payload):
            results, health = payload
            health_text = summarize_health(health)
            populate_table(results)
            if results:
                status_var.set(f"Found {len(results)} results. Sources: {health_text}")
            else:
                res_label = (
                    {
                        "4k": "4K",
                        "1080": "1080p",
                        "any": "any resolution",
                    }.get(resolution_key, "requested")
                    if apply_resolution
                    else "matching"
                )
                status_var.set(f"No {res_label} results. Sources: {health_text}")

        run_background("Searching...", worker, finish, "Search failed")

    def on_browse_top():
        # Fetch and display TPB top items for the selected category.
        top_label = top_type_var.get()
        top_type = selected_value(top_options, top_label)

        def worker():
            raw, health = fetch_top_list(top_type)
            # No resolution filter for top list, but keep sort and sanitize
            results = filter_and_sort(raw, resolution="any")
            return results, health

        def finish(payload):
            results, health = payload
            health_text = summarize_health(health)
            populate_table(results)
            if results:
                status_var.set(f"Top {top_label.lower()} loaded. Sources: {health_text}")
            else:
                status_var.set(f"No top {top_label.lower()} found. Sources: {health_text}")

        run_background(f"Fetching top {top_label.lower()}...", worker, finish, "Browse Top failed")

    def on_row_selected(event):
        selection = table.selection()
        if not selection:
            magnet_var.set("")
            return
        magnets = []
        for item_id in selection:
            info_hash = table.item(item_id, "tags")[0]
            name = table.item(item_id, "values")[0]
            magnets.append(build_magnet(info_hash, name))
        magnet_var.set("\n".join(magnets))

    def copy_magnet():
        magnet = magnet_var.get()
        if not magnet:
            return
        root.clipboard_clear()
        root.clipboard_append(magnet)
        count = magnet.count("\n") + 1
        if count > 1:
            status_var.set(f"{count} magnets copied to clipboard.")
        else:
            status_var.set("Magnet copied to clipboard.")

    # Controls frame
    controls = ttk.Frame(root, padding=10)
    controls.pack(fill="x")

    ttk.Label(controls, text="Query:").pack(side="left")
    query_entry = ttk.Entry(controls, textvariable=query_var, width=40)
    query_entry.pack(side="left", padx=6)
    query_entry.bind("<Return>", lambda event: on_search())

    ttk.Label(controls, text="Type:").pack(side="left", padx=(12, 4))
    category_combo = ttk.Combobox(
        controls,
        textvariable=category_var,
        values=list(category_options.keys()),
        width=10,
        state="readonly",
    )
    category_combo.pack(side="left")

    quality_label = ttk.Label(controls, text="Quality:")
    quality_combo = ttk.Combobox(
        controls,
        textvariable=resolution_var,
        values=list(quality_options.keys()),
        width=7,
        state="readonly",
    )

    def update_quality_visibility(event=None):
        if category_var.get() == "Books":
            quality_label.pack_forget()
            quality_combo.pack_forget()
            return
        if not quality_label.winfo_manager():
            quality_label.pack(side="left", padx=(12, 4), before=search_btn)
            quality_combo.pack(side="left", before=search_btn)

    quality_label.pack(side="left", padx=(12, 4))
    quality_combo.pack(side="left")

    search_btn = ttk.Button(controls, text="Search", command=on_search)
    search_btn.pack(side="left", padx=12)
    category_combo.bind("<<ComboboxSelected>>", update_quality_visibility)
    update_quality_visibility()

    # Theme toggle button
    theme_btn = ttk.Button(controls, text="Dark Mode", command=on_theme_toggle)
    theme_btn.pack(side="right", padx=(6, 0))

    # --- New: Browse Top controls ---
    browse_frame = ttk.Frame(controls)
    browse_frame.pack(side="left", padx=(12, 0))
    ttk.Label(browse_frame, text="Browse Top:").pack(side="left")
    top_combo = ttk.Combobox(
        browse_frame,
        textvariable=top_type_var,
        values=list(top_options.keys()),
        width=8,
        state="readonly",
    )
    top_combo.pack(side="left", padx=(4, 0))
    browse_btn = ttk.Button(browse_frame, text="Go", command=on_browse_top)
    browse_btn.pack(side="left", padx=(6, 0))

    # Table frame
    table_frame = ttk.Frame(root, padding=10)
    table_frame.pack(fill="both", expand=True)

    columns = ("Name", "Seeders", "Leechers", "Size")

    table = ttk.Treeview(
        table_frame,
        columns=columns,
        show="headings",
        selectmode="extended",
        height=18,
    )
    sort_state = {"Name": False, "Seeders": True, "Leechers": True}

    def sort_by_column(col_name: str):
        col_index = columns.index(col_name)
        descending = sort_state.get(col_name, False)

        def sort_key(item_id: str):
            value = table.item(item_id, "values")[col_index]
            if col_name in ("Seeders", "Leechers"):
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return 0
            return str(value).lower()

        items = list(table.get_children(""))
        items.sort(key=sort_key, reverse=descending)
        for index, item_id in enumerate(items):
            table.move(item_id, "", index)
        sort_state[col_name] = not descending

    for col in columns:
        if col in ("Name", "Seeders", "Leechers"):
            table.heading(col, text=col, command=lambda c=col: sort_by_column(c))
        else:
            table.heading(col, text=col)
        anchor = "w" if col == "Name" else "center"
        width = 520 if col == "Name" else 90
        table.column(col, anchor=anchor, width=width)

    vsb = ttk.Scrollbar(table_frame, orient="vertical", command=table.yview)
    table.configure(yscrollcommand=vsb.set)
    table.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    table_frame.rowconfigure(0, weight=1)
    table_frame.columnconfigure(0, weight=1)

    table.bind("<<TreeviewSelect>>", on_row_selected)
    # Removed double-click binding to avoid copying the wrong link

    # Magnet box
    magnet_frame = ttk.Frame(root, padding=10)
    magnet_frame.pack(fill="x")

    ttk.Label(magnet_frame, text="Magnet:").pack(side="left")
    magnet_entry = ttk.Entry(magnet_frame, textvariable=magnet_var)
    magnet_entry.pack(side="left", fill="x", expand=True, padx=6)
    ttk.Button(magnet_frame, text="Copy", command=copy_magnet).pack(side="left")

    # Status bar
    status = ttk.Label(root, textvariable=status_var, relief="sunken", anchor="w")
    status.pack(fill="x", side="bottom")

    apply_theme(theme_var.get())

    return root


if __name__ == "__main__":
    app = create_app()
    app.mainloop()
