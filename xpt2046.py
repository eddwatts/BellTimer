# A simple XPT2046 Touchscreen controller driver for MicroPython
from machine import Pin
import time

class Touch:
    """
    A driver for the XPT2046 resistive touch controller.
    """
    def __init__(self, spi, cs, cal_x1=3780, cal_y1=3880, cal_x2=280, cal_y2=280, x_inv=True, y_inv=True, xy_swap=True):
        """
        Initialize the touch driver.

        Args:
            spi (SPI): The SPI bus shared with the display.
            cs (Pin): The chip select pin for the touch controller.
            cal_x1, cal_y1, cal_x2, cal_y2 (int): Raw calibration values for the touch corners.
            x_inv, y_inv, xy_swap (bool): Flags to orient the touch input correctly.
        """
        self.spi = spi
        self.cs = cs
        self.cs.init(Pin.OUT, value=1)
        
        # Default calibration values that work for many CYD boards
        self.cal_x1 = cal_x1
        self.cal_y1 = cal_y1
        self.cal_x2 = cal_x2
        self.cal_y2 = cal_y2
        
        # Orientation flags
        self.x_inv = x_inv
        self.y_inv = y_inv
        self.xy_swap = xy_swap

    def _read(self, control):
        """Send a command and read 2 bytes of data."""
        self.spi.write(bytes([control]))
        data = self.spi.read(2)
        # The result is 12 bits, so we shift right by 3
        return (data[0] << 8 | data[1]) >> 3

    def get_touch(self, width, height):
        """
        Read the touch coordinates from the controller.

        Args:
            width (int): The width of the screen.
            height (int): The height of the screen.

        Returns:
            tuple(int, int) or None: The (x, y) coordinates of the touch, or None if not touched.
        """
        self.cs.value(0)
        time.sleep_us(10) # Small delay for the chip
        
        # Reading Z1 and Z2 pressures to determine if touched
        self.spi.write(b'\xb1') 
        z1 = self.spi.read(2)
        self.spi.write(b'\xc1')
        z2 = self.spi.read(2)
        
        # Calculate pressure
        pressure = ((z1[0] << 8 | z1[1]) >> 3) + 4095 - ((z2[0] << 8 | z2[1]) >> 3)
        
        # A simple pressure threshold. Adjust if needed.
        if pressure < 100:
             self.cs.value(1)
             return None
        
        x_raw = self._read(0xD1) # Read X
        y_raw = self._read(0x91) # Read Y
        
        self.cs.value(1)
        
        # Map raw ADC values to screen coordinates
        x = self._map_val(x_raw, self.cal_x1, self.cal_x2, 0, width)
        y = self._map_val(y_raw, self.cal_y1, self.cal_y2, 0, height)
        
        # Apply orientation transformations
        if self.x_inv: x = width - x
        if self.y_inv: y = height - y
        if self.xy_swap: x, y = y, x
            
        return int(x), int(y)

    def _map_val(self, val, in_min, in_max, out_min, out_max):
        """Map a value from one range to another."""
        return (val - in_min) * (out_max - out_min) / (in_max - in_min) + out_min
