import json
import re
import tkinter as tk
from html.parser import HTMLParser
from tkinter import ttk, messagebox
import urllib.error
import urllib.parse
import urllib.request

# Multiple TPB proxy endpoints; we try them in order until one works.
API_ENDPOINTS = [
    "https://apibay.org/q.php?q={query}&cat={category}",
    "https://pirateproxy.live/apibay/q.php?q={query}&cat={category}",
    "https://apibay.sbs/q.php?q={query}&cat={category}",
]

# HTML search endpoints, starting with the primary TPB domain.
HTML_ENDPOINTS = [
    "https://thepiratebay.org/search/{query}/1/99/{cat}",
    "https://thepiratebay0.org/search/{query}/1/99/{cat}",
    "https://tpb.party/search/{query}/1/99/{cat}",
]

# TPB category sets to query (we try each until we get results).
CATEGORY_SETS = {
    "movies_hd": ["207", "201", "200"],  # HD Movies, then fallback to Movies/Video
    "shows_hd": ["208", "205", "200"],   # HD TV, fallback to TV/Video
    "all_video": ["200", "0"],            # Broadest search
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
    last_error = None
    for endpoint in HTML_ENDPOINTS:
        for cat in CATEGORY_SETS[category_key]:
            url = endpoint.format(query=encoded_query, cat=cat)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                parser = TPBHTMLParser()
                parser.feed(html)
                if parser.rows:
                    return parser.rows
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                last_error = exc
                continue
    if last_error:
        raise RuntimeError(f"All HTML endpoints failed. Last error: {last_error}")
    return []


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
    last_error = None
    for endpoint in API_ENDPOINTS:
        for cat in CATEGORY_SETS[category_key]:
            url = endpoint.format(query=encoded_query, category=cat)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            try:
                with urllib.request.urlopen(req, timeout=8) as resp:
                    body = resp.read().decode("utf-8", errors="ignore")
                data = json.loads(body)
                if isinstance(data, list) and data:
                    return data
                # If empty, try next category/endpoint.
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                last_error = exc
                continue
            except json.JSONDecodeError as exc:
                last_error = exc
                continue
    html_rows = fetch_html_results(query, category_key)
    if html_rows:
        return html_rows
    if last_error:
        raise RuntimeError(f"All proxy endpoints/categories failed. Last error: {last_error}")
    return []


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
        filtered.append(
            {
                "name": name,
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
    root.title("1080p Magnet Finder")
    root.geometry("900x520")

    query_var = tk.StringVar()
    category_var = tk.StringVar(value="movies_hd")
    status_var = tk.StringVar(value="Ready")
    magnet_var = tk.StringVar()
    resolution_var = tk.StringVar(value="1080")  # options: 4k, 1080, any

    def on_search():
        query = query_var.get().strip()
        if not query:
            messagebox.showinfo("Missing query", "Please enter a search term.")
            return
        try:
            status_var.set("Searching…")
            root.update_idletasks()
            raw = fetch_results(query, category_var.get())
            results = filter_and_sort(raw, resolution=resolution_var.get())
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
            if results:
                status_var.set(f"Found {len(results)} results. Double-click to copy magnet.")
            else:
                res_label = {
                    "4k": "4K",
                    "1080": "1080p",
                    "any": "any resolution",
                }.get(resolution_var.get(), "requested")
                status_var.set(f"No {res_label} results. Try broader category or another filter.")
        except Exception as exc:  # pylint: disable=broad-except
            status_var.set("Error")
            messagebox.showerror("Search failed", str(exc))

    def on_row_selected(event):
        item_id = table.focus()
        if not item_id:
            return
        info_hash = table.item(item_id, "tags")[0]
        name = table.item(item_id, "values")[0]
        magnet = build_magnet(info_hash, name)
        magnet_var.set(magnet)

    def copy_magnet():
        magnet = magnet_var.get()
        if not magnet:
            return
        root.clipboard_clear()
        root.clipboard_append(magnet)
        status_var.set("Magnet copied to clipboard.")

    # Controls frame
    controls = ttk.Frame(root, padding=10)
    controls.pack(fill="x")

    ttk.Label(controls, text="Query:").pack(side="left")
    ttk.Entry(controls, textvariable=query_var, width=40).pack(side="left", padx=6)

    ttk.Radiobutton(
        controls, text="Movies (HD)", value="movies_hd", variable=category_var
    ).pack(side="left", padx=(12, 4))
    ttk.Radiobutton(
        controls, text="TV Shows (HD)", value="shows_hd", variable=category_var
    ).pack(side="left", padx=4)
    ttk.Radiobutton(
        controls, text="All Video", value="all_video", variable=category_var
    ).pack(side="left", padx=4)

    # Resolution filter
    res_frame = ttk.Frame(controls)
    res_frame.pack(side="left", padx=(12, 0))
    ttk.Radiobutton(res_frame, text="4K", value="4k", variable=resolution_var).pack(side="left")
    ttk.Radiobutton(res_frame, text="1080p", value="1080", variable=resolution_var).pack(side="left")
    ttk.Radiobutton(res_frame, text="Any", value="any", variable=resolution_var).pack(side="left")

    ttk.Button(controls, text="Search", command=on_search).pack(side="left", padx=12)

    # Table frame
    table_frame = ttk.Frame(root, padding=10)
    table_frame.pack(fill="both", expand=True)

    columns = ("Name", "Seeders", "Leechers", "Size")
    table = ttk.Treeview(
        table_frame,
        columns=columns,
        show="headings",
        selectmode="browse",
        height=18,
    )
    for col in columns:
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
    table.bind("<Double-1>", on_row_selected)

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

    return root


if __name__ == "__main__":
    app = create_app()
    app.mainloop()
