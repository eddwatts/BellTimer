# config.py

# --- Wi-Fi Network Credentials (Used as a fallback if wifi_config.json doesn't exist) ---
WIFI_SSID = "backup"
WIFI_PASSWORD = "backuppassword"

# --- URLs and Servers ---
# NEW: This URL should now point to a manifest JSON file that lists all available schedules.
# Example manifest: {"base_url": "https://example.com/schedules/", "schedules": {"Normal Day": "normal.json", "Half Day": "half_day.json"}}
SCHEDULE_MANIFEST_URL = "https://example.com/schedule_manifest.php"
NTP_HOST = "0.uk.pool.ntp.org"

# --- Security Configuration ---
# X-API-Key: your_long_random_api_key_here
WEB_INTERFACE_PASSWORD = "your_password_here"  # Change this!
API_KEY = "your_long_random_api_key_here"      # Change this!

# --- OTA (Over-the-Air) Update Configuration ---
# IMPORTANT: Change this URL to your own public GitHub repository.
OTA_REPO_URL = "https://github.com/eddwatts/BellTimer"
# List of all files that should be updated from the repository.
OTA_UPDATE_FILES = ["main.py", "config.py", "xpt2046.py", "st7789.py", "romand.py", "ota_updater.py"]

# --- SD Card & Logging Configuration ---
# Pins for the built-in SD card reader on the CYD. This typically uses SPI bus 2 (HSPI).
SD_SPI_BUS = 2
SD_SCLK_PIN = 40
SD_MOSI_PIN = 41
SD_MISO_PIN = 38
SD_CS_PIN = 39
LOG_FILE = "/sd/event_log.txt"
LOG_FILE_MAX_SIZE_KB = 512 # Rotate log file after it reaches this size

# --- Timezone Configuration ---
TIMEZONE = "Europe/London"

# --- Relay Configuration ---
RELAY_1_PIN = 26
RELAY_2_PIN = 27
RELAY_ON_DURATION = 1

# --- RGB LED Configuration (Active Low) ---
# Pins for the three separate RGB LED GPIOs.
RGB_LED_R_PIN = 4
RGB_LED_G_PIN = 16
RGB_LED_B_PIN = 17
# Status Colors (R, G, B) - Non-zero values mean ON.
COLOR_NORMAL = (0, 10, 0)      # Green
COLOR_HOLIDAY = (0, 0, 10)     # Blue
COLOR_SYNCING = (20, 10, 0)    # Yellow
COLOR_WIFI_CONNECTING = (10, 0, 10) # Magenta
COLOR_WIFI_FAILED = (20, 0, 0) # Red
COLOR_AP_MODE = (10, 10, 10)   # White

# --- Display & SPI Configuration ---
# The display uses SPI bus 1 (VSPI).
DISPLAY_SPI_BUS, DISPLAY_SPI_BAUDRATE = 1, 24000000
DISPLAY_SCLK_PIN, DISPLAY_MOSI_PIN = 14, 13
DISPLAY_RESET_PIN, DISPLAY_CS_PIN, DISPLAY_DC_PIN, DISPLAY_BACKLIGHT_PIN = 12, 15, 2, 21
DISPLAY_WIDTH, DISPLAY_HEIGHT = 240, 240

# --- Touchscreen Configuration ---
TOUCH_CS_PIN = 32

# --- Screen Burn-in Prevention ---
SCREEN_OFF_TIMEOUT = 300
PIXEL_SHIFT_INTERVAL_S = 60

# --- Display Colors ---
BLACK, BLUE, RED, GREEN, CYAN, MAGENTA, YELLOW, WHITE, ORANGE = 0x0000, 0x001F, 0xF800, 0x07E0, 0x07FF, 0xF81F, 0xFFE0, 0xFFFF, 0xFD20


