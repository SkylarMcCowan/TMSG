# Magnet Finder

A lightweight Tkinter GUI application to search configured TPB-style endpoints and retrieve magnet links for video, music, and books.

Current version: **1.1 - QoL Update**

## Features

- **Multi-source search**: Queries configured API and HTML endpoints, then merges unique results by info hash
- **Endpoint health indicator**: Status bar shows which sources returned results, were empty, or failed
- **Background searches**: Network requests run off the UI thread so the app stays responsive
- **Compact selectors**: Dropdowns for type, quality, and Browse Top keep the toolbar cleaner
- **Smart quality control**: Hides the quality selector when searching Books
- **Resolution filtering**: Filter video results by 1080p, 4K, or any resolution
- **Category selection**: Search Movies, TV Shows, All Video, Music, or Books
- **Browse Top**: Load top Movies, Shows, Music, or Books from configured HTML endpoints
- **Dark mode**: Toggle between light and dark UI themes
- **Fullscreen launch**: Starts fullscreen; press `Esc` to leave fullscreen
- **Keyboard search**: Press `Enter` in the query box to start searching
- **Sortable table**: Sort results by name, seeders, or leechers
- **Magnet copy**: Select one or more rows, then click **Copy** to copy magnet links

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
- `threading` and `queue` (background search processing)

### 4. Run the application

```bash
python main.py
```

A GUI window will open. Enter a search query, select filters, and click **Search**.

## Usage

### Basic Workflow

1. **Enter a search query** (e.g., "The Matrix 1080p")
2. **Choose a type**: Movie, TV Show, All Video, Music, or Books
3. **Select quality**: 1080p, 4K, or Any. This control is hidden for Books.
4. **Click Search** or press `Enter` in the query box
5. **Select one or more rows** to populate the magnet link field
6. **Click Copy** to copy the magnet to your clipboard
7. **Paste into your torrent client** and download

### Browse Top

1. Choose Movies, Shows, Music, or Books from **Browse Top**
2. Click **Go**
3. Select result rows and click **Copy**

### Search Tips

- Be specific: "Dune 2021 1080p" works better than "Dune"
- Try broader types if no results appear, such as All Video
- Use Any quality if a search is too narrow
- Higher seeder count = faster download
- Check file size to confirm it matches your expectations
- Watch the status bar to see which endpoints worked or failed

## Configuration

### Proxy Endpoints

Endpoints are configured near the top of `main.py`. Each endpoint has a display name and URL template.

```python
API_ENDPOINTS = [
    {"name": "apibay.org", "url": "https://apibay.org/q.php?q={query}&cat={category}"},
    {
        "name": "pirateproxy.live",
        "url": "https://pirateproxy.live/apibay/q.php?q={query}&cat={category}",
    },
    {"name": "apibay.sbs", "url": "https://apibay.sbs/q.php?q={query}&cat={category}"},
]
```

Searches merge results across all working sources instead of stopping at the first successful endpoint.

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
- Switch to "All Video" type instead of Movie/TV Show
- Switch quality to Any
- Check your internet connection
- Check endpoint health in the status bar
- Try again in a few minutes because endpoints can be temporarily down

### GUI doesn't appear

- Ensure tkinter is properly installed (see above)
- Try running from terminal directly: `python main.py` (not in background)
- On macOS, grant Terminal permission to access other apps if prompted

### Magnet link looks incomplete

The magnet link may appear truncated in the text field but is complete. Click **Copy** and paste it into your torrent client to verify.

## Changelog

### 1.1 - QoL Update

- Replaced crowded radio buttons with compact dropdown selectors
- Added background search processing to avoid UI stutter
- Added endpoint health reporting in the status bar
- Broadened searches by merging results from all configured endpoints
- Added Browse Top selectors for Movies, Shows, Music, and Books
- Added dark mode
- Added fullscreen startup with `Esc` to exit fullscreen
- Added `Enter` key search from the query box
- Hid quality selection for Books

### 1.0

- Initial search UI
- API endpoint search with HTML fallback
- Resolution filtering
- Magnet generation and clipboard copy

## Roadmap

- **1.2 - Search polish**
  - Search history dropdown
  - Min seeders and max size filters
  - Include/exclude keyword filters
  - Clear Search / Reset Filters action

- **1.3 - Result management**
  - Favorites saved to a local JSON file
  - Export visible results to CSV or JSON
  - Result details panel with info hash, size, seeders, leechers, and full magnet

- **1.4 - Endpoint tools**
  - Endpoint settings editor in the UI
  - Manual endpoint health check
  - Per-endpoint enable/disable toggles

- **Later**
  - Open selected magnet directly in the system torrent client
  - Optional compact/windowed startup mode
  - Better duplicate grouping by normalized title and size

## Legal Notice

This tool is for **educational purposes only**. Users are responsible for complying with local copyright laws. Only download content you have the right to access.

## License

MIT

## Contributing

Feel free to submit issues or improvements!
