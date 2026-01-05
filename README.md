# 1080p Magnet Finder

A lightweight GUI application to search The Pirate Bay and retrieve magnet links for movies and TV shows.

## Features

- **Multi-proxy support**: Automatically tries multiple TPB proxy endpoints if one fails
- **Resolution filtering**: Filter results by 1080p, 4K, or any resolution
- **Seeders sorting**: Results sorted by seeder count (highest first)
- **Category selection**: Search by Movies (HD), TV Shows (HD), or All Video
- **One-click magnet copy**: Double-click a result to copy the magnet link to clipboard
- **HTML fallback**: Falls back to HTML scraping if JSON API endpoints fail

## Requirements

- **Python 3.12+** (with tkinter support)
- **macOS, Linux, or Windows**

## Installation

### 1. Clone or download the repository

```bash
git clone <repo-url>
cd Pirate_API_Downloader
```

### 2. Create a Python virtual environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

No external packages required! The app uses only Python's standard library:
- `urllib` (HTTP requests)
- `json` (JSON parsing)
- `tkinter` (GUI)
- `html.parser` (HTML parsing)
- `re` (regex)

### 4. Run the application

```bash
python main.py
```

A GUI window will open. Enter a search query, select filters, and click **Search**.

## Usage

### Basic Workflow

1. **Enter a search query** (e.g., "The Matrix 1080p")
2. **Choose a category**: Movies (HD), TV Shows (HD), or All Video
3. **Select resolution filter**: 1080p, 4K, or Any
4. **Click Search** – Results appear in the table, sorted by seeders
5. **Double-click a result** to populate the magnet link field
6. **Click Copy** to copy the magnet to your clipboard
7. **Paste into your torrent client** and download

### Search Tips

- Be specific: "Dune 2021 1080p" works better than "Dune"
- Try broader categories if no results appear
- Higher seeder count = faster download
- Check file size to confirm it matches your expectations

## Configuration

### Proxy Endpoints

If a proxy is down, the app tries these in order (in `API_ENDPOINTS` and `HTML_ENDPOINTS` lists):

```python
API_ENDPOINTS = [
    "https://apibay.org/q.php?q={query}&cat={category}",
    "https://pirateproxy.live/apibay/q.php?q={query}&cat={category}",
    "https://apibay.sbs/q.php?q={query}&cat={category}",
]
```

### Trackers

Default trackers are embedded in magnet links:

```python
TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.demonii.com:1337/announce",
    "udp://tracker.coppersurfer.tk:6969/announce",
    "udp://tracker.leechers-paradise.org:6969/announce",
]
```

## Troubleshooting

### "ModuleNotFoundError: No module named '_tkinter'"

**Problem**: Python was installed without tkinter support.

**Solution (macOS with Homebrew)**:
```bash
brew install python@3.12 python-tk@3.12
/opt/homebrew/opt/python@3.12/bin/python3.12 -m venv venv
source venv/bin/activate
python main.py
```

**Solution (Ubuntu/Debian)**:
```bash
sudo apt-get install python3.12-tk
python3.12 -m venv venv
source venv/bin/activate
python main.py
```

**Solution (Windows)**:
Download Python from [python.org](https://www.python.org) and check the "tcl/tk and IDLE" option during installation.

### No search results

- Try a broader search term (e.g., "Matrix" instead of "The Matrix 1080p Remastered")
- Switch to "All Video" category instead of Movies/TV
- Check your internet connection
- Try again in a few minutes (proxies can be temporarily down)

### GUI doesn't appear

- Ensure tkinter is properly installed (see above)
- Try running from terminal directly: `python main.py` (not in background)
- On macOS, grant Terminal permission to access other apps if prompted

### Magnet link looks incomplete

The magnet link may appear truncated in the text field but is complete. Click **Copy** and paste it into your torrent client to verify.

## Legal Notice

This tool is for **educational purposes only**. Users are responsible for complying with local copyright laws. Only download content you have the right to access.

## License

MIT

## Contributing

Feel free to submit issues or improvements!
