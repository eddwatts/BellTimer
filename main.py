# main.py (Ported for ESP32-CYD)
# Features: Color Display, DST, Watchdog, Web UI, Schedule Cache, Diagnostics, Touchscreen, AP Setup, Multiple Schedules, OTA Updates

import network
import urequests
import utime
import ntptime
import socket
import ujson
import ssl
import gc
import sys
import esp32
from machine import Pin, SPI, WDT, PWM, reset
import st7789
import romand as font
import xpt2046
import ota_updater # Import the new OTA library
import config

# --- Global Variables ---
relay1, relay2 = Pin(config.RELAY_1_PIN, Pin.OUT, value=0), Pin(config.RELAY_2_PIN, Pin.OUT, value=0)
schedule, next_bell_event, schedule_manifest = {}, {}, {}
display, backlight, touch = None, None, None
display_on, last_activity_time = True, utime.time()
led = Pin(2, Pin.OUT)
holiday_mode, ip_address = False, "Connecting..."
last_status_line, last_status_color = "Booting...", config.YELLOW
wifi_connection_failed = False
wifi_creds = {'ssid': config.WIFI_SSID, 'password': config.WIFI_PASSWORD}
active_schedule_name = "Default"

# Diagnostic & Touch Globals
start_time, last_sync_time_str, wifi_rssi = utime.ticks_ms(), "Never", 0
relay_status = {'1': 'OFF', '2': 'OFF'}
SYNC_BUTTON_RECT, HOLIDAY_BUTTON_RECT, SETUP_BUTTON_RECT = (config.DISPLAY_WIDTH-85,5,80,40), (5,5,80,40), (config.DISPLAY_WIDTH//2-75,100,150,40)
touch_lock, long_press_triggered, touch_start_time, held_button = False, False, 0, None
pixel_shift_x, pixel_shift_y, pixel_shift_direction, last_pixel_shift_time = 0, 0, 0, utime.time()

# --- File Constants ---
DAYS_OF_WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
HOLIDAY_STATUS_FILE, SCHEDULE_CACHE_FILE, WIFI_CONFIG_FILE, ACTIVE_SCHEDULE_FILE = "holiday.dat", "schedule.json", "wifi.json", "active_schedule.txt"

# --- Wi-Fi & Schedule Config Management ---
def load_wifi_credentials():
    global wifi_creds
    try:
        with open(WIFI_CONFIG_FILE, 'r') as f: wifi_creds = ujson.load(f)
        print(f"Loaded WiFi credentials for '{wifi_creds['ssid']}'")
    except (OSError, ValueError): print("Using fallback WiFi credentials")

def save_wifi_credentials(ssid, password):
    try:
        with open(WIFI_CONFIG_FILE, 'w') as f: ujson.dump({'ssid': ssid, 'password': password}, f)
        print("Saved new WiFi credentials.")
    except Exception as e: print(f"Error saving WiFi credentials: {e}")

def load_active_schedule_name():
    global active_schedule_name
    try:
        with open(ACTIVE_SCHEDULE_FILE, 'r') as f: active_schedule_name = f.read().strip()
        print(f"Loaded active schedule: {active_schedule_name}")
    except OSError:
        print("No active schedule file found, will use first in manifest.")

def save_active_schedule_name(name):
    global active_schedule_name; active_schedule_name = name
    try:
        with open(ACTIVE_SCHEDULE_FILE, 'w') as f: f.write(name)
        print(f"Set active schedule to: {name}")
    except Exception as e: print(f"Error saving active schedule: {e}")

# --- Schedule & Holiday Functions ---
def save_schedule_to_cache(data):
    try:
        with open(SCHEDULE_CACHE_FILE, "w") as f: ujson.dump(data, f)
        print("Schedule saved to cache.")
    except Exception as e: print(f"Error saving schedule to cache: {e}")

def load_schedule_from_cache():
    global schedule
    try:
        with open(SCHEDULE_CACHE_FILE, "r") as f: schedule = ujson.load(f)
        print("Loaded schedule from cache."); find_next_bell()
    except (OSError, ValueError): print("Could not load schedule from cache."); schedule = {}

def save_holiday_status(status):
    global holiday_mode; holiday_mode = status
    try:
        with open(HOLIDAY_STATUS_FILE, "w") as f: f.write("1" if status else "0")
    except Exception as e: print(f"Error saving holiday status: {e}")

def load_holiday_status():
    global holiday_mode
    try:
        with open(HOLIDAY_STATUS_FILE, "r") as f: holiday_mode = f.read().strip() == "1"
    except Exception: save_holiday_status(False)

# --- Time & DST Functions (Unchanged) ---
def is_bst(dt):
    year, month, day, hour, _, _, _, _ = dt
    if month < 3 or month > 10: return False
    if month > 3 and month < 10: return True
    last_sunday = 31 - (utime.localtime(utime.mktime((year, month, 31, 1, 0, 0, 0, 0)))[6] + 1) % 7
    if month == 3: return day > last_sunday or (day == last_sunday and hour >= 1)
    if month == 10: return day < last_sunday or (day == last_sunday and hour < 1)
    return False

def get_local_time():
    utc_now_tuple = utime.localtime()
    if config.TIMEZONE == "Europe/London" and is_bst(utc_now_tuple):
        return utime.localtime(utime.mktime(utc_now_tuple) + 3600)
    return utc_now_tuple

# --- Display & System Functions ---
def init_display():
    global display, backlight, touch
    try:
        spi = SPI(config.SPI_BUS, baudrate=config.SPI_BAUDRATE, sck=Pin(config.SPI_SCLK_PIN), mosi=Pin(config.SPI_MOSI_PIN))
        display = st7789.ST7789(spi, config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT, reset=Pin(config.RESET_PIN, Pin.OUT), cs=Pin(config.CS_PIN, Pin.OUT), dc=Pin(config.DC_PIN, Pin.OUT))
        display.init()
        touch = xpt2046.Touch(spi, cs=Pin(config.TOUCH_CS_PIN))
        if config.BACKLIGHT_PIN != -1:
             backlight = PWM(Pin(config.BACKLIGHT_PIN)); backlight.freq(1000); backlight.duty_u16(65535)
        display.fill(config.BLACK); print("Hardware initialized."); wake_display()
    except Exception as e: print(f"Error initializing hardware: {e}"); display = None

def wake_display():
    global display_on, last_activity_time
    if backlight and not display_on: backlight.duty_u16(65535); display_on = True
    last_activity_time = utime.time()

def manage_display_power():
    global display_on
    if backlight and display_on and (utime.time() - last_activity_time > config.SCREEN_OFF_TIMEOUT):
        backlight.duty_u16(0); display_on = False

def manage_pixel_shift():
    global last_pixel_shift_time, pixel_shift_direction, pixel_shift_x, pixel_shift_y
    shift_interval = getattr(config, 'PIXEL_SHIFT_INTERVAL_S', 0)
    if not display_on or shift_interval <= 0: return
    if utime.time() - last_pixel_shift_time > shift_interval:
        pixel_shift_direction = (pixel_shift_direction + 1) % 4
        shifts = [(1,0), (1,1), (0,1), (0,0)]; pixel_shift_x, pixel_shift_y = shifts[pixel_shift_direction]
        last_pixel_shift_time = utime.time()

def update_display(status_line, status_color=config.GREEN):
    global last_status_line, last_status_color; last_status_line, last_status_color = status_line, status_color
    if not display: return
    wake_display(); display.fill(config.BLACK)
    px, py = pixel_shift_x, pixel_shift_y

    if wifi_connection_failed:
        msg = "WiFi Connection Failed"
        st7789.write(display, font, msg, (config.DISPLAY_WIDTH-st7789.width(font,msg))//2+px, 60+py, config.RED, config.BLACK)
        btn_x,btn_y,btn_w,btn_h = SETUP_BUTTON_RECT; display.fill_rect(btn_x+px,btn_y+py,btn_w,btn_h,config.ORANGE)
        btn_text = "Setup WiFi"; st7789.write(display,font,btn_text,btn_x+(btn_w-st7789.width(font,btn_text))//2+px,btn_y+(btn_h-16)//2+py,config.BLACK,config.ORANGE)
        return

    now = get_local_time(); day_name = DAYS_OF_WEEK[now[6]]
    date_str, time_str = f"{day_name} {now[2]:02d}/{now[1]:02d}/{now[0]}", f"{now[3]:02d}:{now[4]:02d}:{now[5]:02d}"
    st7789.write(display,font,date_str,5+px,50+py,config.CYAN,config.BLACK)
    st7789.write(display,font,time_str,5+px,75+py,config.WHITE,config.BLACK)
    
    btn_x,btn_y,btn_w,btn_h=SYNC_BUTTON_RECT;display.fill_rect(btn_x+px,btn_y+py,btn_w,btn_h,config.BLUE);st7789.write(display,font,"Sync",btn_x+(btn_w-st7789.width(font,"Sync"))//2+px,btn_y+(btn_h-16)//2+py,config.WHITE,config.BLUE)
    btn_x,btn_y,btn_w,btn_h=HOLIDAY_BUTTON_RECT;btn_color=config.RED if holiday_mode else config.GREEN;display.fill_rect(btn_x+px,btn_y+py,btn_w,btn_h,btn_color);st7789.write(display,font,"Holiday",btn_x+(btn_w-st7789.width(font,"Holiday"))//2+px,btn_y+(btn_h-16)//2+py,config.WHITE,btn_color)

    st7789.write(display,font,f"Schedule: {active_schedule_name}",5+px,100+py,config.MAGENTA,config.BLACK)
    if holiday_mode:
        msg1,msg2 = "--- HOLIDAY MODE ---","     IS ACTIVE"; st7789.write(display,font,msg1,((config.DISPLAY_WIDTH-st7789.width(font,msg1))//2)+px,125+py,config.RED,config.BLACK); st7789.write(display,font,msg2,((config.DISPLAY_WIDTH-st7789.width(font,msg2))//2)+px,150+py,config.RED,config.BLACK)
    else:
        st7789.write(display, font, "Next Bell:", 5 + px, 120 + py, config.YELLOW, config.BLACK)
        if next_bell_event:
            day,time,name = next_bell_event.get('day_name',''),next_bell_event.get('time','N/A'),next_bell_event.get('bellname','No Name')
            st7789.write(display,font,f"{day} at {time}",15+px,145+py,config.WHITE,config.BLACK); st7789.write(display,font,f"Name: {name[:18]}",15+px,165+py,config.WHITE,config.BLACK)
        else: st7789.write(display, font, "None scheduled", 15 + px, 145 + py, config.WHITE, config.BLACK)
    
    wifi_str,sync_str=f"WiFi:{wifi_rssi}dBm",f"Sync:{last_sync_time_str}";st7789.write(display,font,wifi_str,5+px,190+py,config.MAGENTA,config.BLACK);st7789.write(display,font,sync_str,config.DISPLAY_WIDTH-st7789.width(font,sync_str)-5+px,190+py,config.MAGENTA,config.BLACK)
    st7789.write(display,font,"Status:",5+px,215+py,config.YELLOW,config.BLACK); st7789.write(display,font,status_line,80+px,215+py,status_color,config.BLACK);st7789.write(display,font,ip_address,config.DISPLAY_WIDTH-st7789.width(font,ip_address)-5+px,215+py,config.CYAN,config.BLACK)

# --- Core Logic ---
def get_uptime_str():
    s=utime.ticks_diff(utime.ticks_ms(),start_time)//1000;d,h,m,s=s//86400,(s%86400)//3600,(s%3600)//60,s%60;return f"{d}d {h}h {m}m {s}s"

def find_next_bell():
    global next_bell_event;
    if not schedule:next_bell_event={};return
    now,now_mins=get_local_time(),get_local_time()[3]*60+get_local_time()[4]
    for day_offset in range(7):
        day_idx=(now[6]+day_offset)%7;day_str=str(day_idx)
        if day_str in schedule and schedule.get(day_str):
            for event in sorted(schedule[day_str],key=lambda x:x.get('time','')):
                t=event['time'].split(':');event_mins=int(t[0])*60+int(t[1])
                if day_offset==0 and event_mins<=now_mins:continue
                next_bell_event=event;next_bell_event['day_name']=DAYS_OF_WEEK[day_idx];return
    next_bell_event={}

def connect_wifi(wdt):
    global ip_address, wifi_connection_failed
    wlan = network.WLAN(network.STA_IF); wlan.active(True)
    if not wlan.isconnected():
        update_display(f"Connecting...", config.YELLOW)
        wlan.connect(wifi_creds['ssid'], wifi_creds['password'])
        max_wait = 15
        while max_wait > 0:
            wdt.feed()
            if wlan.status() >= 3: break
            max_wait -= 1; utime.sleep(1)
    if wlan.status() != 3:
        ip_address="Failed";wifi_connection_failed=True;update_display("WiFi Connect Fail",config.RED);return False
    else:
        ip_address=wlan.ifconfig()[0];wifi_connection_failed=False;update_display("WiFi Connected",config.GREEN);print(f"WiFi OK: {ip_address}");return True

def sync_time(wdt):
    global last_sync_time_str; update_display("Syncing time...", config.YELLOW)
    for _ in range(3):
        wdt.feed()
        try:
            ntptime.host=config.NTP_HOST; ntptime.settime()
            now=get_local_time(); last_sync_time_str=f"{now[3]:02d}:{now[4]:02d}"
            update_display("Time Synced OK",config.GREEN); return True
        except Exception: utime.sleep(3)
    update_display("NTP Sync Fail",config.RED); return False

def https_get_json(url):
    try:
        _,_,host,path=url.split('/',3);addr=socket.getaddrinfo(host,443)[0][-1];s=socket.socket();s.settimeout(10);s.connect(addr);s=ssl.wrap_socket(s,server_hostname=host);s.write(f"GET /{path} HTTP/1.0\r\nHost: {host}\r\n\r\n".encode());response=b"";
        while True:
            chunk=s.read(1024);
            if not chunk:break
            response+=chunk
        s.close();return ujson.loads(response[response.find(b'\r\n\r\n')+4:])
    except Exception: return None

def fetch_manifest_and_schedule(wdt):
    global schedule, schedule_manifest, active_schedule_name
    update_display("Fetching manifest...", config.YELLOW)
    
    new_manifest = https_get_json(config.SCHEDULE_MANIFEST_URL)
    if not new_manifest or "schedules" not in new_manifest or "base_url" not in new_manifest:
        update_display("Manifest Invalid", config.ORANGE); return False
    schedule_manifest = new_manifest
    
    if active_schedule_name not in schedule_manifest["schedules"]:
        active_schedule_name = next(iter(schedule_manifest["schedules"]))
        save_active_schedule_name(active_schedule_name)

    schedule_filename = schedule_manifest["schedules"][active_schedule_name]
    schedule_url = schedule_manifest["base_url"] + schedule_filename
    update_display(f"Fetching {active_schedule_name}...", config.YELLOW)
    
    new_schedule = https_get_json(schedule_url)
    if new_schedule:
        schedule = new_schedule; save_schedule_to_cache(schedule); find_next_bell()
        update_display("Schedule OK", config.GREEN); return True
    else:
        update_display("Schedule DL Fail", config.ORANGE); return False

def activate_relay(relay_number, duration):
    target=relay1 if relay_number==1 else relay2;relay_status[str(relay_number)]='ON';update_display(f"Relay {relay_number} ON",config.ORANGE);target.value(1);utime.sleep(duration);target.value(0);relay_status[str(relay_number)]='OFF'

# --- OTA Update Function ---
def perform_ota_update(cl, wdt):
    cl.send("HTTP/1.0 200 OK\r\nContent-type: text/html\r\nConnection: close\r\n\r\n")
    cl.send("<html><body><h1>Starting OTA Update...</h1><p>Check the device screen for progress. The device will reboot if successful.</p></body></html>")
    cl.close()
    
    display.fill(config.BLACK)
    st7789.write(display, font, "Starting OTA Update...", 10, 120, config.YELLOW, config.BLACK)
    
    updater = ota_updater.OTAUpdater(config.OTA_REPO_URL, config.OTA_UPDATE_FILES)
    if updater.check_for_updates():
        st7789.write(display, font, "Downloading...", 10, 140, config.WHITE, config.BLACK)
        if updater.download_and_install_updates():
            st7789.write(display, font, "Update successful!", 10, 160, config.GREEN, config.BLACK)
            st7789.write(display, font, "Rebooting...", 10, 180, config.WHITE, config.BLACK)
            utime.sleep(3); reset()
        else:
            st7789.write(display, font, "Update failed!", 10, 160, config.RED, config.BLACK)
            utime.sleep(5)
    else:
        st7789.write(display, font, "No updates available.", 10, 140, config.GREEN, config.BLACK)
        utime.sleep(3)
    
    update_display(last_status_line, last_status_color)

# --- Web Server ---
def send_status_page(cl):
    now=get_local_time();time_str=f"{now[0]:04d}-{now[1]:02d}-{now[2]:02d} {now[3]:02d}:{now[4]:02d}:{now[5]:02d}"
    next_bell_str = "DISABLED" if holiday_mode else (f"{next_bell_event.get('day_name','')} at {next_bell_event.get('time','')} - {next_bell_event.get('bellname','No Name')}" if next_bell_event else "None")
    
    cl.send("HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n<!DOCTYPE html><html><head><title>Bell Controller</title><meta name='viewport' content='width=device-width, initial-scale=1.0'><style>body{font-family:sans-serif;background-color:#333;color:#fff;margin:15px;} button,input,select{padding:10px;margin:5px;border-radius:5px;border:none;cursor:pointer;} table{width:100%;border-collapse:collapse;} th,td{padding:8px;border:1px solid #555;text-align:left;}</style></head><body>")
    cl.send(f"<h1>Bell Controller</h1><p><strong>Time:</strong> {time_str}</p><p><strong>Next Bell:</strong> {next_bell_str}</p><hr><h2>Holiday Mode: {'ON' if holiday_mode else 'OFF'}</h2>")
    cl.send(f"<form action='/{'holidayoff' if holiday_mode else 'holidayon'}'><button style='background-color:{'green' if holiday_mode else 'red'};color:white;'>Turn {'OFF' if holiday_mode else 'ON'}</button></form>")
    
    cl.send(f"<hr><h2>Schedule Management</h2><p><strong>Active:</strong> {active_schedule_name}</p><form action='/set_schedule' method='post'><label for='schedule'>Change:</label><select id='schedule' name='schedule_name'>")
    if schedule_manifest and "schedules" in schedule_manifest:
        for name in schedule_manifest["schedules"]: cl.send(f"<option value='{name}' {'selected' if name==active_schedule_name else ''}>{name}</option>")
    cl.send("</select><input type='submit' value='Set Active'></form>")
    cl.send("<p><strong>Quick Sets:</strong></p><form action='/set_schedule_normal' style='display:inline-block;'><button>Set Normal Day</button></form><form action='/set_schedule_half' style='display:inline-block;'><button>Set Half Day</button></form>")

    cl.send("<hr><h2>Controls</h2><form action='/force-update'><button>Force Update</button></form><form action='/test-relay1' style='display:inline-block;'><button>Test Relay 1</button></form><form action='/test-relay2' style='display:inline-block;'><button>Test Relay 2</button></form>")
    cl.send("<hr><h2>Software Update</h2><form action='/ota_update'><button style='background-color:#555;color:white;'>Check for Updates</button></form>")
    cl.send("<hr><h2>Diagnostics</h2><p><a href='/diagnostics'>View Full Diagnostics</a></p></body></html>")

def send_diagnostics_page(cl):
    cl.send("HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n<!DOCTYPE html><html><head><title>Diagnostics</title><meta http-equiv='refresh' content='10' name='viewport' content='width=device-width, initial-scale=1.0'><style>body{font-family:sans-serif;background-color:#333;color:#fff;margin:15px;} table{width:100%;border-collapse:collapse;margin-bottom:20px;} th,td{padding:8px;border:1px solid #555;text-align:left;} h2{color:#00ffff;}</style></head><body><h1>Diagnostics</h1>")
    gc.collect(); temp_c=(esp32.raw_temperature()-32.0)*5.0/9.0; wlan=network.WLAN(network.STA_IF); ip,subnet,gateway,dns=wlan.ifconfig() if wlan.isconnected() else ('N/A','N/A','N/A','N/A')
    cl.send(f"<h2>System</h2><table><tr><td>MicroPython</td><td>{sys.version}</td></tr><tr><td>Uptime</td><td>{get_uptime_str()}</td></tr><tr><td>CPU Freq</td><td>{machine.freq()/1000000}MHz</td></tr><tr><td>CPU Temp</td><td>{temp_c:.1f}&deg;C</td></tr><tr><td>Free Mem</td><td>{gc.mem_free()} bytes</td></tr></table>")
    cl.send(f"<h2>Network</h2><table><tr><td>IP</td><td>{ip}</td></tr><tr><td>Subnet</td><td>{subnet}</td></tr><tr><td>Gateway</td><td>{gateway}</td></tr><tr><td>DNS</td><td>{dns}</td></tr><tr><td>RSSI</td><td>{wifi_rssi}dBm</td></tr></table>")
    cl.send(f"<h2>Application</h2><table><tr><td>Relay 1</td><td>{relay_status['1']}</td></tr><tr><td>Relay 2</td><td>{relay_status['2']}</td></tr><tr><td>Holiday Mode</td><td>{'ON' if holiday_mode else 'OFF'}</td></tr><tr><td>Last Sync</td><td>{last_sync_time_str}</td></tr><tr><td>Active Schedule</td><td>{active_schedule_name}</td></tr></table><p><a href='/'>&laquo; Back</a></p></body></html>")

def handle_web_request(cl, wdt):
    gc.collect()
    try:
        req_line = cl.readline().decode()
        path = req_line.split(' ')[1]; wake_display()
        
        if 'POST' in req_line and path == '/set_schedule':
            content_len=0
            while True:
                h=cl.readline().decode()
                if h.startswith('Content-Length:'): content_len=int(h.split(':')[1].strip())
                if h=='\r\n':break
            data=cl.read(content_len).decode()
            new_name=urequests.unquote_plus(data.split('=')[1])
            save_active_schedule_name(new_name); fetch_manifest_and_schedule(wdt)
            cl.send('HTTP/1.0 303 See Other\r\nLocation: /\r\n\r\n')
        else:
            while True: 
                if cl.readline() == b'\r\n': break
            
            def set_schedule_action(name):
                if name in schedule_manifest.get("schedules",{}):
                    save_active_schedule_name(name)
                    fetch_manifest_and_schedule(wdt)
                    return f"Schedule set to {name}"
                return "Schedule name not found"

            actions = {
                '/force-update': lambda: (sync_time(wdt), fetch_manifest_and_schedule(wdt), "Update Triggered")[2],
                '/test-relay1': lambda: (activate_relay(1,config.RELAY_ON_DURATION), "Relay 1 Tested")[1],
                '/test-relay2': lambda: (activate_relay(2,config.RELAY_ON_DURATION), "Relay 2 Tested")[1],
                '/holidayon': lambda: (save_holiday_status(True), "Holiday ON")[1],
                '/holidayoff': lambda: (save_holiday_status(False), "Holiday OFF")[1],
                '/set_schedule_normal': lambda: set_schedule_action("Normal Day"),
                '/set_schedule_half': lambda: set_schedule_action("Half Day"),
            }
            if path in actions:
                res_txt = actions[path]()
                cl.send(f"HTTP/1.0 200 OK\r\n\r\n<h1>{res_txt}</h1><p><a href='/'>Back</a></p>")
            elif path == '/ota_update': perform_ota_update(cl, wdt); return
            elif path == '/': send_status_page(cl)
            elif path == '/diagnostics': send_diagnostics_page(cl)
            elif path == '/holidaystatus': 
                cl.send('HTTP/1.0 200 OK\r\nContent-type: application/json\r\n\r\n')
                cl.send(ujson.dumps({"holiday_mode":holiday_mode}))
            else: cl.send('HTTP/1.0 404 Not Found\r\n\r\n<h1>404</h1>')
    except Exception as e: print(f"Web error: {e}")
    finally: cl.close(); gc.collect()

def run_setup_mode(wdt):
    global display
    print("Entering WiFi setup mode...")
    network.WLAN(network.STA_IF).active(False)
    ap = network.WLAN(network.AP_IF)
    ap.config(essid="Bell_Controller_Setup")
    ap.active(True)
    
    while not ap.active(): pass
    setup_ip = ap.ifconfig()[0]
    
    display.fill(config.BLACK)
    st7789.write(display, font, "WiFi Setup", (config.DISPLAY_WIDTH-st7789.width(font,"WiFi Setup"))//2, 10, config.YELLOW, config.BLACK)
    st7789.write(display, font, "1. Connect phone/PC to", 10, 40, config.WHITE, config.BLACK)
    st7789.write(display, font, "   WiFi: Bell_Controller_Setup", 10, 65, config.CYAN, config.BLACK)
    st7789.write(display, font, "2. Open a web browser", 10, 105, config.WHITE, config.BLACK)
    st7789.write(display, font, "3. Go to this address:", 10, 145, config.WHITE, config.BLACK)
    st7789.write(display, font, f"   http://{setup_ip}", 10, 170, config.CYAN, config.BLACK)
    st7789.write(display, font, "Waiting for user...", (config.DISPLAY_WIDTH-st7789.width(font,"Waiting for user..."))//2, 210, config.WHITE, config.BLACK)

    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s = socket.socket()
    s.bind(addr); s.listen(1)
    
    while True:
        wdt.feed()
        cl, addr = s.accept()
        try:
            req_line = cl.readline().decode()
            if 'POST /save' in req_line:
                content_len = 0
                while True:
                    header = cl.readline().decode()
                    if header.startswith('Content-Length:'):
                        content_len = int(header.split(':')[1].strip())
                    if header == '\r\n': break
                
                data = cl.read(content_len).decode()
                parts = data.split('&')
                ssid = urequests.unquote_plus(parts[0].split('=')[1])
                password = urequests.unquote_plus(parts[1].split('=')[1])
                
                save_wifi_credentials(ssid, password)
                
                cl.send('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n')
                cl.send('<html><body><h1>Credentials Saved!</h1><p>The device will now reboot and connect to the new network.</p></body></html>')
                cl.close()
                
                display.fill(config.BLACK)
                st7789.write(display, font, "Saved! Rebooting...", 10, 120, config.GREEN, config.BLACK)
                utime.sleep(3)
                reset()

            else: # Serve the setup page
                wlan = network.WLAN(network.STA_IF)
                wlan.active(True)
                scan_results = wlan.scan()
                wlan.active(False)
                
                options = ""
                for res in scan_results:
                    ssid = res[0].decode('utf-8')
                    options += f'<option value="{ssid}">{ssid}</option>'
                
                html = f"""<!DOCTYPE html><html><head><title>WiFi Setup</title><meta name="viewport" content="width=device-width, initial-scale=1"></head>
                <body><h1>Bell Controller WiFi Setup</h1>
                <form action="/save" method="post">
                <label for="ssid">Select WiFi Network:</label><br>
                <select id="ssid" name="ssid">{options}</select><br><br>
                <label for="password">Password:</label><br>
                <input type="password" id="password" name="password"><br><br>
                <input type="submit" value="Save and Reboot">
                </form></body></html>"""
                cl.send('HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n')
                cl.send(html)
                cl.close()
        except Exception as e:
            print(f"Setup web server error: {e}")
            cl.close()

def handle_touch(wdt):
    global touch_lock, display_on, touch_start_time, held_button, long_press_triggered
    if not touch: return
    pos = touch.get_touch(config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT)
    
    if pos:
        if not display_on:
            wake_display(); touch_lock=True; return

        x, y = pos
        if not touch_lock:
            touch_lock = True
            
            s_btn_x, s_btn_y, s_btn_w, s_btn_h = SYNC_BUTTON_RECT
            h_btn_x, h_btn_y, h_btn_w, h_btn_h = HOLIDAY_BUTTON_RECT
            u_btn_x, u_btn_y, u_btn_w, u_btn_h = SETUP_BUTTON_RECT
            
            if wifi_connection_failed and u_btn_x <= x <= u_btn_x + u_btn_w and u_btn_y <= y <= u_btn_y + u_btn_h:
                held_button = 'setup'
            elif s_btn_x <= x <= s_btn_x + s_btn_w and s_btn_y <= y <= s_btn_y + s_btn_h:
                held_button = 'sync'; touch_start_time=utime.ticks_ms()
            elif h_btn_x <= x <= h_btn_x + h_btn_w and h_btn_y <= y <= h_btn_y + h_btn_h:
                held_button = 'holiday'; touch_start_time=utime.ticks_ms()
                display.fill_rect(h_btn_x,h_btn_y,h_btn_w,h_btn_h,config.YELLOW);st7789.write(display,font,"Holiday",h_btn_x+(h_btn_w-st7789.width(font,"Holiday"))//2,h_btn_y+(h_btn_h-16)//2,config.BLACK,config.YELLOW)

        if held_button == 'holiday' and not long_press_triggered:
            if utime.ticks_diff(utime.ticks_ms(), touch_start_time) > 2000:
                long_press_triggered = True; save_holiday_status(not holiday_mode); update_display(last_status_line, last_status_color)

    else: # Touch released
        if held_button == 'setup':
            run_setup_mode(wdt)
        elif held_button == 'sync' and not long_press_triggered:
            s_btn_x, s_btn_y, s_btn_w, s_btn_h = SYNC_BUTTON_RECT
            display.fill_rect(s_btn_x,s_btn_y,s_btn_w,s_btn_h,config.RED);st7789.write(display,font,"Sync",s_btn_x+(s_btn_w-st7789.width(font,"Sync"))//2,s_btn_y+(s_btn_h-16)//2,config.WHITE,config.RED);sync_time(wdt);fetch_manifest_and_schedule(wdt)
        
        if touch_lock: update_display(last_status_line, last_status_color)
        touch_lock, held_button, touch_start_time, long_press_triggered = False, None, 0, False

# --- Main Execution ---
wdt = WDT(timeout=8388)
init_display()
load_wifi_credentials()
load_holiday_status()
load_schedule_from_cache()
load_active_schedule_name()

if connect_wifi(wdt):
    if sync_time(wdt): fetch_manifest_and_schedule(wdt)
    update_display("Idle", config.GREEN)
else:
    update_display("WiFi Connect Fail", config.RED)

if not wifi_connection_failed:
    addr=socket.getaddrinfo('0.0.0.0',80)[0][-1];s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(addr);s.listen(1);s.setblocking(False)
    print(f'Web server on http://{ip_address}')
else: s = None

last_check_minute, last_wifi_check, last_rssi_check = -1, utime.time(), utime.time()

while True:
    wdt.feed()
    if display_on: led.toggle()
    
    if not wifi_connection_failed and s:
        try: cl,addr=s.accept(); handle_web_request(cl,wdt)
        except OSError: pass

    handle_touch(wdt)
    manage_display_power()
    manage_pixel_shift()
    
    current_ticks = utime.time()
    if not wifi_connection_failed:
        if current_ticks - last_wifi_check > 300:
            if not network.WLAN(network.STA_IF).isconnected(): connect_wifi(wdt)
            last_wifi_check=current_ticks
        if current_ticks - last_rssi_check > 30:
            wlan=network.WLAN(network.STA_IF)
            if wlan.isconnected(): wifi_rssi = wlan.status('rssi')
            last_rssi_check=current_ticks

        now=get_local_time()
        if now[4]!=last_check_minute:
            last_check_minute=now[4]
            if display_on: update_display(last_status_line, last_status_color)
            if not holiday_mode:
                current_time_str=f"{now[3]:02d}:{now[4]:02d}"
                if current_time_str=="07:30":
                    if sync_time(wdt): fetch_manifest_and_schedule(wdt)
                
                day_str=str(now[6])
                if day_str in schedule and schedule.get(day_str,[]):
                    for entry in schedule[day_str]:
                        if entry.get('time')==current_time_str:
                            d,r=entry.get('belllength',config.RELAY_ON_DURATION),entry.get('relay')
                            if r: activate_relay(r,d); find_next_bell(); update_display("Idle", config.GREEN)
    else: 
        if display_on: update_display("WiFi Connect Fail", config.RED)
    utime.sleep(0.1)

