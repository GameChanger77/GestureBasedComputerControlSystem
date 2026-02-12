from pynput.mouse import Controller as Mouse, Button
from pynput.keyboard import Controller as Keyboard, Key

class Action:
    def __init__(self, osType): #TODO remove osType argument since we can auto-detect
        self.mouse = Mouse()
        self.keyboard = Keyboard()
        
    def move_cursor(self, x: int, y: int):
        """
        Public method to move the cursor.
        Called directly by gesture recognizers.

        Args:
            x: Screen x coordinate in pixels
            y: Screen y coordinate in pixels
        """
        self.mouse.position = (x, y)

    def left_click(self, x: int = None, y: int = None):
        """
        Public method to perform left click.
        Called directly by gesture recognizers.

        Args:
            x: Screen x coordinate in pixels (optional, uses current position if not provided)
            y: Screen y coordinate in pixels (optional, uses current position if not provided)
        """
        if x is not None and y is not None:
            self.move_cursor(x, y)
    
        self.mouse.click(Button.left, 1)

    def double_click(self, x: int = None, y: int = None):
        """
        Public method to perform double click.
        Called directly by gesture recognizers.

        Args:
            x: Screen x coordinate in pixels
            y: Screen y coordinate in pixels
        """
        if x is not None and y is not None:
            self.move_cursor(x, y)
        self.mouse.click(Button.left, 2)

    def right_click(self, x: int = None, y: int = None):
        """
        Public method to perform right click.
        Called directly by gesture recognizers.

        Args:
            x: Screen x coordinate in pixels (optional, uses current position if not provided)
            y: Screen y coordinate in pixels (optional, uses current position if not provided)
        """
        if x is not None and y is not None:
            self.move_cursor(x, y)
        self.mouse.click(Button.right, 1)

    def scroll(self, delta_x: int = 0, delta_y: int = 0):
        """
        Public method to perform scroll.
        Called directly by gesture recognizers.

        Args:
            delta_x: Horizontal scroll amount (positive = right, negative = left)
            delta_y: Vertical scroll amount (positive = up, negative = down)
        """
        self.mouse.scroll(delta_x, delta_y) 
        
    def hold_left_click(self):
        """
        Public method to hold left click (press without release).
        Called directly by gesture recognizers.
        """
        self.mouse.press(Button.left)
        
    def release_left_click(self):
        """
        Public method to release left click (release after hold).
        Called directly by gesture recognizers.
        """
        self.mouse.release(Button.left)
        
    def hold_right_click(self):
        """
        Public method to hold right click (press without release).
        Called directly by gesture recognizers.
        """
        self.mouse.press(Button.right)
        
    def release_right_click(self):
        """
        Public method to release right click (release after hold).
        Called directly by gesture recognizers.
        """
        self.mouse.release(Button.right)

    def press_key(self, key):
        """
        Public method to press a key.
        Called directly by gesture recognizers.

        Args:
            key: The key to press (can be a character or a special key from pynput.keyboard.Key)
        """
        self.keyboard.press(key)
        
    def release_key(self, key):
        """
        Public method to release a key.
        Called directly by gesture recognizers.

        Args:
            key: The key to release (can be a character or a special key from pynput.keyboard.Key)
        """
        self.keyboard.release(key)
        
    def press_and_release_key(self, key):
        """
        Public method to press and release a key.
        Called directly by gesture recognizers.

        Args:
            key: The key to press and release (can be a character or a special key from pynput.keyboard.Key)
        """
        self.press_key(key)
        self.release_key(key)
     
    def perform_macro(self, keys: list):
        """
        Public method to perform a macro (a sequence of key presses).
        Called directly by gesture recognizers.

        Args:
            keys: A list of keys to press and release in sequence
        """
        for key in keys:
            self.press_and_release_key(key)
        
    # def type_text(self, text: str):
    #     """
    #     Public method to type a string of text.
    #     Called directly by gesture recognizers.

    #     Args:
    #         text: The string of text to type
    #     """
    #     self.keyboard.type(text)