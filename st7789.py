# Combined file for ST7789 driver and a font.
# Driver Source: https://github.com/russhughes/st7789py_mpy
# Font: romand.py from the same repository.
# Save this file on your ESP32 as "st7789.py"
# Then, save the font part separately as "romand.py"

# --- Part 1: ST7789 Driver (st7789.py) ---

import time
from micropython import const

# commands
ST7789_SLPIN = const(0x10)
ST7789_SLPOUT = const(0x11)
ST7789_NORON = const(0x13)
ST7789_INVOFF = const(0x20)
ST7789_INVON = const(0x21)
ST7789_DISPOFF = const(0x28)
ST7789_DISPON = const(0x29)
ST7789_CASET = const(0x2A)
ST7789_RASET = const(0x2B)
ST7789_RAMWR = const(0x2C)
ST7789_COLMOD = const(0x3A)
ST7789_MADCTL = const(0x36)

# MADCTL bits
ST7789_MADCTL_MY = const(0x80)
ST7789_MADCTL_MX = const(0x40)
ST7789_MADCTL_MV = const(0x20)
ST7789_MADCTL_ML = const(0x10)
ST7789_MADCTL_BGR = const(0x08)
ST7789_MADCTL_MH = const(0x04)
ST7789_MADCTL_RGB = const(0x00)

class ST7789:
    def __init__(self, spi, width, height, reset, cs, dc, backlight=None, rotation=0):
        self.spi = spi
        self.width = width
        self.height = height
        self.reset = reset
        self.cs = cs
        self.dc = dc
        self.backlight = backlight
        self.rotation = rotation

    def _write_cmd(self, cmd):
        self.cs(0)
        self.dc(0)
        self.spi.write(bytearray([cmd]))
        self.cs(1)

    def _write_data(self, data):
        self.cs(0)
        self.dc(1)
        self.spi.write(data)
        self.cs(1)
        
    def init(self):
        self.reset(1)
        time.sleep_ms(50)
        self.reset(0)
        time.sleep_ms(50)
        self.reset(1)
        time.sleep_ms(150)
        
        self._write_cmd(ST7789_SLPOUT)
        time.sleep_ms(120)

        self._write_cmd(ST7789_COLMOD)
        self._write_data(b'\x55') # 16-bit color

        self._write_cmd(ST7789_MADCTL)
        self._write_data(bytearray([self._rotation()]))

        self._write_cmd(ST7789_CASET)
        self._write_data(b'\x00\x00' + self.width.to_bytes(2, 'big'))

        self._write_cmd(ST7789_RASET)
        self._write_data(b'\x00\x00' + self.height.to_bytes(2, 'big'))

        self._write_cmd(ST7789_NORON)
        time.sleep_ms(10)
        
        self._write_cmd(ST7789_DISPON)
        time.sleep_ms(120)

    def _rotation(self):
        if self.rotation == 0: return ST7789_MADCTL_RGB
        if self.rotation == 1: return ST7789_MADCTL_MX | ST7789_MADCTL_MV | ST7789_MADCTL_RGB
        if self.rotation == 2: return ST7789_MADCTL_MX | ST7789_MADCTL_MY | ST7789_MADCTL_RGB
        if self.rotation == 3: return ST7789_MADCTL_MY | ST7789_MADCTL_MV | ST7789_MADCTL_RGB
        return ST7789_MADCTL_RGB

    def _set_window(self, x, y, w, h):
        self._write_cmd(ST7789_CASET)
        self._write_data((x).to_bytes(2, 'big') + (x+w-1).to_bytes(2, 'big'))
        self._write_cmd(ST7789_RASET)
        self._write_data((y).to_bytes(2, 'big') + (y+h-1).to_bytes(2, 'big'))
        self._write_cmd(ST7789_RAMWR)

    def fill(self, color):
        self._set_window(0, 0, self.width, self.height)
        chunk_size = 512
        chunks = (self.width * self.height) // chunk_size
        color_bytes = color.to_bytes(2, 'big')
        buffer = bytearray(color_bytes * chunk_size)
        
        self.cs(0)
        self.dc(1)
        for _ in range(chunks):
            self.spi.write(buffer)
        rem = (self.width * self.height) % chunk_size
        if rem > 0:
            self.spi.write(bytearray(color_bytes * rem))
        self.cs(1)


# Helper functions to use with the font file
def write(display, font, text, x, y, fg=0xFFFF, bg=0x0000):
    for char in text:
        font.render_char(display, char, x, y, fg, bg)
        x += font.width(char)

def width(font, text):
    return sum(font.width(char) for char in text)