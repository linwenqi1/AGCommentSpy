# AppGallery Comments Scraper

A Python automation tool to scrape application information and user comments from the Huawei AppGallery on HarmonyOS (OpenHarmony).

## Acknowledgments

This project heavily relies on the open-source project **[hmdriver2](https://github.com/codematrixer/hmdriver2)** for interacting with HarmonyOS devices via HDC (HarmonyOS Device Connector). 

## Prerequisites

1. **Python 3.x**
2. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```
3. **UI Viewer Tool (Optional but recommended):**
   To easily inspect the UI hierarchy and locate XPath elements on HarmonyOS devices, use the `uiviewer` tool:
   ```bash
   pip3 install -U uiviewer
   ```
   After installation, you can run `uiviewer` in your terminal to open the UI inspector.

4. **Device Configuration:**
   Before running the scripts, make sure your Huawei/HarmonyOS device is connected and accessible via `hdc`.
   Update the `DEVICE_ID` in `config.py` with your actual device ID:
   ```python
   # config.py
   DEVICE_ID = "YOUR_DEVICE_ID"
   ```

## Usage

You can run the scraper for a single application or in batch mode for multiple applications.

### 1. Single Application Mode

Use `main.py` to scrape a specific app by providing its package name. 

**Basic Usage:**
```bash
python main.py -p com.tencent.wechat
```

**Advanced Usage:**
```bash
python main.py -p <PACKAGE_NAME> -m <MAX_SWIPES> -t <TASK>
```

**Arguments:**
- `-p` / `--package`: **(Required)** Target application package name (e.g., `com.tencent.wechat`).
- `-m` / `--max-swipes`: Maximum number of scroll swipes to perform to load comments (default is `20`).
- `-t` / `--task`: The specific scraping task. Options are `app_info`, `comments`, or `both` (default is `both`).

**Examples:**
- Scrape only app info:
  ```bash
  python main.py -p com.tencent.wechat -t app_info
  ```
- Scrape only comments up to 15 swipes:
  ```bash
  python main.py -p com.tencent.wechat -m 15 -t comments
  ```

### 2. Batch Mode

To scrape multiple apps sequentially, configure your target apps in `app.json`. The JSON file should look like this:

```json
[
  { "name": "WeChat", "package": "com.tencent.wechat" },
  { "name": "Alipay", "package": "com.alipay.mobile.client" }
]
```

Then, run the batch script:

```bash
python run_batch.py
```

**Batch Script Features:**
- Automatically iterates through all apps defined in `app.json`.
- If an app's directory already contains `app_info.json` and `comments.json`, it correctly assumes it is completed and safely skips it (resumable scraping).
- Smoothly handles process lifecycle (including `Ctrl+C` termination).

## Project Structure

When the scraping is successful, outputs are saved into folders named after the package name. 

```
project/
├── app.json                  # List of applications for batch processing
├── config.py                 # Core configurations (Device ID, XPaths, Screen bounds)
├── main.py                   # Entry point for single-app scraping
├── comments.py               # Core logic for parsing and collecting comments
├── run_batch.py              # Script to run scraper over multiple packages iteratively
├── hmdriver2/                # Open-source HarmonyOS driver library
└── com.tencent.wechat/       # Generated automatically -> Ouput directory for WeChat
    ├── app_info.json         # Scraped app title and subtitle
    └── comments.json         # Scraped list of comments (username, date, rating, content, device)
```
