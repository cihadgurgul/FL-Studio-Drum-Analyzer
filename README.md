# FL Drum Analyzer

A command-line tool that scans your FL Studio projects to find out which drum kits and samples you actually use — and helps you clean up the ones you don't.

If you're like most producers, you've downloaded way more drum kits than you'll ever use. This tool tells you exactly which ones are collecting dust so you can archive them and free up disk space.

## What It Does

- **Scans** all your `.flp` project files (including ones inside `.zip` archives) and tracks every drum sample used
- **Ranks** your most-used samples and kits
- **Finds unused kits** — ones you've never touched or haven't used in months
- **Safely archives** unused kits to a folder you choose (with undo support)

## Requirements

- **Windows** (FL Studio is Windows/Mac, and this tool auto-detects your FL Studio install)
- **Python 3.10 or newer** — [Download Python](https://www.python.org/downloads/)
  - During install, make sure to check **"Add Python to PATH"**
- **FL Studio** installed in the default location

## Setup (Step by Step)

### 1. Download this tool

Click the green **Code** button at the top of this page, then click **Download ZIP**.

Unzip it to a folder you'll remember — for example, `C:/Tools/fl-drum-analyzer`.

Or if you use git:

```
git clone https://github.com/cihadgurgul/fl-drum-analyzer.git
cd fl-drum-analyzer
```

### 2. Install dependencies

Open a terminal in the folder (right-click in the folder → **Open in Terminal**), then run:

```
pip install -r requirements.txt
```

### 3. Set up your config

Copy the example config file and rename it:

```
copy config.example.json config.json
```

Open `config.json` in any text editor (Notepad works fine) and fill in your paths:

```json
{
    "flp_directory": "C:/Users/YourName/Documents/Image-Line/FL Studio/Projects",
    "drum_kits_directories": [
        "C:/Users/YourName/Drum Kits",
        "C:/Program Files/Image-Line/FL Studio 2024/Data/Patches/Packs/My Drums"
    ],
    "unused_directory": "C:/Users/YourName/Drum Kits/_unused",
    "unused_threshold_days": 90
}
```

| Setting | What to put |
|---------|-------------|
| `flp_directory` | The folder where your FL Studio projects live |
| `drum_kits_directories` | One or more folders where your drum kits are stored |
| `unused_directory` | Where you want unused kits moved to (will be created automatically) |
| `unused_threshold_days` | How many days before a kit is considered "unused" (default: 90) |

**Important:** Use forward slashes `/` in your paths, not backslashes `\`.

### 4. Find your paths

Not sure where your stuff is? Here's how to find out:

- **FL Studio projects:** Open FL Studio → Options → File Settings → look at the "Backup" or "Data" folder path. Your projects are usually in `Documents/Image-Line/FL Studio/Projects`.
- **Drum kits:** Wherever you unzipped them. Check FL Studio's browser panel — right-click a folder to see its location on disk.

## Usage

Open a terminal in the tool's folder and run these commands:

### Scan your projects

```
python main.py scan
```

This reads all your `.flp` files (including any `.flp` files inside `.zip` archives) and builds a database of which samples are used where. First scan may take a minute depending on how many projects you have. After that, it only re-scans files that changed.

### See your most-used samples

```
python main.py stats
```

Shows your top 10 most-used samples. Want more?

```
python main.py stats --top 20
python main.py stats --all
```

### See your most-used kits

```
python main.py kits
python main.py kits --all
```

### Find unused kits

```
python main.py unused
```

Shows kits that either:
- Haven't been used in any project modified within your threshold (default: 90 days)
- Were never used in any project at all

### Clean up unused kits

```
python main.py cleanup
```

This does a **dry run** first — it shows you what *would* be moved, without actually moving anything. When you're ready:

```
python main.py cleanup --confirm
```

This moves unused kits to your `unused_directory`.

### Undo a cleanup

Changed your mind? No problem:

```
python main.py undo
```

This moves everything back to where it was.

## Example Output

```
$ python main.py stats

Top Samples by Project Count:
  #  Sample                          Projects
---  ------------------------------  ----------
  1  808 Mafia Kit/808_dark.wav             23
  2  Nick Mira Kit/hihat_01.wav             19
  3  Metro Boomin Kit/kick_sub.wav          15
  ...
```

```
$ python main.py unused

Unused Kits (threshold: 90 days):
Kit                  Last Used    Status
-------------------  -----------  ----------
Old Trap Kit 2019    2024-08-12   Stale
Random Producer Kit  —            Never used

2 kit(s) eligible for archival.
```

## FAQ

**Will this mess up my FL Studio projects?**
No. This tool only *reads* your `.flp` files — it never modifies them. The only thing it moves are the drum kit folders themselves, and only when you explicitly run `cleanup --confirm`.

**What if I clean up a kit and then need it?**
Run `python main.py undo` and it'll move everything back. The kits are moved, not deleted — they're always in your `unused_directory` until you decide to permanently delete them.

**Does it scan all my samples or just drums?**
It only tracks samples that live inside your configured `drum_kits_directories`. Samples stored elsewhere (like FL Studio's default packs) are ignored unless you add those paths.

**Can I add multiple drum kit folders?**
Yes. Add as many paths as you want to the `drum_kits_directories` array in `config.json`.

**It says "No .flp files found"?**
Double-check that `flp_directory` in your `config.json` points to the right folder, and make sure you're using forward slashes `/`.

## License

MIT — do whatever you want with it.
