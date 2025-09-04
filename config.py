# config.py

# --- Wi-Fi Network Credentials (Used as a fallback if wifi_config.json doesn't exist) ---
WIFI_SSID = "backup"
WIFI_PASSWORD = "backuppassword"

# --- URLs and Servers ---
# NEW: This URL should now point to a manifest JSON file that lists all available schedules.
# Example manifest: {"base_url": "https://example.com/schedules/", "schedules": {"Normal Day": "normal.json", "Half Day": "half_day.json"}}
SCHEDULE_MANIFEST_URL = "https://example.com/schedule_manifest.php"
NTP_HOST = "0.uk.pool.ntp.org"

# --- OTA (Over-the-Air) Update Configuration ---
# IMPORTANT: Change this URL to your own public GitHub repository.
OTA_REPO_URL = "https://github.com/eddwatts/BellTimer"
# List of all files that should be updated from the repository.
OTA_UPDATE_FILES = ["main.py", "config.py", "xpt2046.py", "st7789.py", "romand.py", "ota_updater.py"]

# --- SD Card & Logging Configuration ---
# Pins for the built-in SD card reader on the CYD
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

# --- Display & SPI Configuration ---
# Common pins for ESP32-Cheap-Yellow-Display
SPI_BUS = 1
SPI_BAUDRATE = 24000000
SPI_SCLK_PIN = 14
SPI_MOSI_PIN = 13
RESET_PIN = 12
CS_PIN = 15  # Chip select for the display
DC_PIN = 2   # Data/Command for the display
BACKLIGHT_PIN = 21
DISPLAY_WIDTH = 240
DISPLAY_HEIGHT = 240

# --- Touchscreen Configuration ---
# Pin for the XPT2046 touch controller chip select
TOUCH_CS_PIN = 32

# --- Screen Burn-in Prevention ---
SCREEN_OFF_TIMEOUT = 300  # 5 minutes
PIXEL_SHIFT_INTERVAL_S = 60 # Shift pixel every 60 seconds

# --- Display Colors ---
BLACK, BLUE, RED, GREEN, CYAN, MAGENTA, YELLOW, WHITE, ORANGE = 0x0000, 0x001F, 0xF800, 0x07E0, 0x07FF, 0xF81F, 0xFFE0, 0xFFFF, 0xFD20


