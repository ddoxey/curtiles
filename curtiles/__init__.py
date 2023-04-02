"""
The CTiles module is an abstraction for creating an ncurses based application
based on configuation that specifies a set of "tiles" that are text tiles to
be displayed and updated in real time.

The objective is to create as distinct separation between the application code
and the presentation layer code.

Author: Dylan Doxey
Date: Feb 22, 2023
See: https://github.com/ddoxey/curtiles
"""
import re
import sys
import time
import curses
import datetime
from threading import Thread
from queue import Queue, Empty as EmptyQueue
from curses import wrapper, ERR as CursesErr

class CTiles:
    """CTiles provides a configuration driven framework
       for making a "tiled" ncurses UI.
    """

    class Command:
        """Command class provides abstractions for mapping keyboard keys
           to command actions.
        """
        QUIT        = ord('Q')
        TOGGLE_HALT = ord(' ')

    class Grid:
        """Grid class creates a temporary representation of the terminal
           real estate and can automatically arrange the tiles from left
           to right and top to bottom.
        """
        def __init__(self, height, width, border=False):
            self.data = [[0 for x in range(width)] for y in range(height)]
            self.has_border = border
            self.height = height
            self.width = width
            if self.has_border:
                self.height -= 2
                self.width -= 2

        def __str__(self):
            lines = ['+' + ('-' * (1 + self.width * 2)) + '+']
            b = ""
            if self.has_border:
                b = " "
                lines.append('|{} {} {}|'.format(b, " " * self.width, b))
            for row in self.data:
                lines.append('|{} {} {}|'.format(b, " ".join([str(c) for c in row]), b))
            if self.has_border:
                lines.append(lines[1])
            lines.append(lines[0])
            return "\n".join(lines)

        def inquire(self, ypos, xpos, slab):
            """Inquire if a given Tile can fit at the proposed y/x position.
               Return None if the answer is no, or a loss score greater than
               zero if the Tile would overlap the edges of the screen.
            """
            loss = 0
            for row in range(slab.height):
                r_index = row + ypos
                if r_index >= len(self.data):
                    loss += slab.width
                    continue
                c_index = xpos
                c_end = c_index + slab.width
                c_index = max(c_index, 0)
                collisions = sum(self.data[r_index][c_index:c_end])
                if collisions > 0:
                    return None
                overhang = slab.width - len(self.data[r_index][c_index:])
                loss += overhang
            return loss

        def search(self, slab):
            """Search for the nearest available place to position the Tile by
               scanning from left to right and top to bottom.
            """
            border_offset = 1 if self.has_border else 0
            positions = []
            for row in range(self.height):
                for col in range(self.width):
                    loss = self.inquire(row, col, slab)
                    if loss is not None:
                        positions.append({'ypos': row + border_offset,
                                          'xpos': col + border_offset,
                                          'loss': loss})
                        if loss == 0:
                            break
                if len(positions) > 0 and positions[-1]['loss'] == 0:
                    break
            if len(positions) > 0:
                return sorted(positions, key=lambda c: c['loss'])[0]
            return None

        def reserve(self, slab):
            """Reserve a spot on the grid for the Tile."""
            for row in range(slab.ypos, slab.ypos + slab.height):
                for col in range(slab.xpos, slab.xpos + slab.width):
                    if row < len(self.data) and col < len(self.data[row]):
                        if self.data[row][col] > 0:
                            raise AssertionError(f'{row},{col} is already reserved')
                        self.data[row][col] = 1

    class Stylist:
        """The Stylist initializes the styling pairs in the curses environment
           and provides a style database for later reference.
        """
        border_char_for = {
            'double': {
                'horz': 0x2550,
                'vert': 0x2551,
                'tl': 0x2554,
                'tr': 0x2557,
                'br': 0x255D,
                'bl': 0x255A,
            },
            'single': {
                'horz': 0x2500,
                'vert': 0x2502,
                'ltee': 0x251C,
                'rtee': 0x2524,
                'tl': 0x256D,
                'tr': 0x256E,
                'br': 0x256F,
                'bl': 0x2570,
            },
        }
        xlate_attr_for = {
            'NORMAL': curses.A_NORMAL,
            'STANDOUT': curses.A_STANDOUT,
            'UNDERLINE': curses.A_UNDERLINE,
            'REVERSE': curses.A_REVERSE,
            'BLINK': curses.A_BLINK,
            'DIM': curses.A_DIM,
            'BOLD': curses.A_BOLD,
            'ALTCHARSET': curses.A_ALTCHARSET,
            'INVIS': curses.A_INVIS,
            'PROTECT': curses.A_PROTECT,
            'HORIZONTAL': curses.A_HORIZONTAL,
            'LEFT': curses.A_LEFT,
            'LOW': curses.A_LOW,
            'RIGHT': curses.A_RIGHT,
            'TOP': curses.A_TOP,
            'VERTICAL': curses.A_VERTICAL,
        }
        xlate_color_for = {
            'BLACK': curses.COLOR_BLACK,
            'RED': curses.COLOR_RED,
            'GREEN': curses.COLOR_GREEN,
            'YELLOW': curses.COLOR_YELLOW,
            'BLUE': curses.COLOR_BLUE,
            'MAGENTA': curses.COLOR_MAGENTA,
            'CYAN': curses.COLOR_CYAN,
            'WHITE': curses.COLOR_WHITE,
        }
        x11_color_rgb = {
            'ALICE_BLUE': [240, 247, 255],
            'ANTIQUE_WHITE': [250, 235, 214],
            'AQUA': [0, 255, 255],
            'AQUAMARINE': [128, 255, 212],
            'AZURE': [240, 255, 255],
            'BEIGE': [245, 245, 219],
            'BISQUE': [255, 227, 196],
            'BLANCHED_ALMOND': [255, 235, 204],
            'BLUE_VIOLET': [138, 43, 227],
            'BROWN': [166, 41, 41],
            'BURLYWOOD': [222, 184, 135],
            'CADET_BLUE': [94, 158, 161],
            'CHARTREUSE': [128, 255, 0],
            'CHOCOLATE': [209, 105, 31],
            'CORAL': [255, 128, 79],
            'CORNFLOWER_BLUE': [99, 148, 237],
            'CORNSILK': [255, 247, 219],
            'CRIMSON': [219, 20, 61],
            'DARK_BLUE': [0, 0, 140],
            'DARK_CYAN': [0, 140, 140],
            'DARK_GOLDENROD': [184, 135, 10],
            'DARK_GRAY': [168, 168, 168],
            'DARK_GREEN': [0, 99, 0],
            'DARK_KHAKI': [189, 184, 107],
            'DARK_MAGENTA': [140, 0, 140],
            'DARK_OLIVE_GREEN': [84, 107, 46],
            'DARK_ORANGE': [255, 140, 0],
            'DARK_ORCHID': [153, 51, 204],
            'DARK_RED': [140, 0, 0],
            'DARK_SALMON': [232, 150, 122],
            'DARK_SEA_GREEN': [143, 189, 143],
            'DARK_SLATE_BLUE': [71, 61, 140],
            'DARK_SLATE_GRAY': [46, 79, 79],
            'DARK_TURQUOISE': [0, 207, 209],
            'DARK_VIOLET': [148, 0, 212],
            'DEEP_PINK': [255, 20, 148],
            'DEEP_SKY_BLUE': [0, 191, 255],
            'DIM_GRAY': [105, 105, 105],
            'DODGER_BLUE': [31, 143, 255],
            'FIREBRICK': [178, 33, 33],
            'FLORAL_WHITE': [255, 250, 240],
            'FOREST_GREEN': [33, 140, 33],
            'FUCHSIA': [255, 0, 255],
            'GAINSBORO*': [219, 219, 219],
            'GHOST_WHITE': [247, 247, 255],
            'GOLD': [255, 214, 0],
            'GOLDENROD': [217, 166, 33],
            'GRAY': [191, 191, 191],
            'WEB_GRAY': [128, 128, 128],
            'WEB_GREEN': [0, 128, 0],
            'GREEN_YELLOW': [173, 255, 46],
            'HONEYDEW': [240, 255, 240],
            'HOT_PINK': [255, 105, 181],
            'INDIAN_RED': [204, 92, 92],
            'INDIGO': [74, 0, 130],
            'IVORY': [255, 255, 240],
            'KHAKI': [240, 230, 140],
            'LAVENDER': [230, 230, 250],
            'LAVENDER_BLUSH': [255, 240, 245],
            'LAWN_GREEN': [125, 252, 0],
            'LEMON_CHIFFON': [255, 250, 204],
            'LIGHT_BLUE': [173, 217, 230],
            'LIGHT_CORAL': [240, 128, 128],
            'LIGHT_CYAN': [224, 255, 255],
            'LIGHT_GOLDENROD': [250, 250, 209],
            'LIGHT_GRAY': [212, 212, 212],
            'LIGHT_GREEN': [143, 237, 143],
            'LIGHT_PINK': [255, 181, 194],
            'LIGHT_SALMON': [255, 161, 122],
            'LIGHT_SEA_GREEN': [33, 178, 171],
            'LIGHT_SKY_BLUE': [135, 207, 250],
            'LIGHT_SLATE_GRAY': [120, 135, 153],
            'LIGHT_STEEL_BLUE': [176, 196, 222],
            'LIGHT_YELLOW': [255, 255, 224],
            'LIME': [0, 255, 0],
            'LIME_GREEN': [51, 204, 51],
            'LINEN': [250, 240, 230],
            'MAROON': [176, 48, 97],
            'WEB_MAROON': [128, 0, 0],
            'MEDIUM_AQUAMARINE': [102, 204, 171],
            'MEDIUM_BLUE': [0, 0, 204],
            'MEDIUM_ORCHID': [186, 84, 212],
            'MEDIUM_PURPLE': [148, 112, 219],
            'MEDIUM_SEA_GREEN': [61, 178, 112],
            'MEDIUM_SLATE_BLUE': [122, 105, 237],
            'MEDIUM_SPRING_GREEN': [0, 250, 153],
            'MEDIUM_TURQUOISE': [71, 209, 204],
            'MEDIUM_VIOLET_RED': [199, 20, 133],
            'MIDNIGHT_BLUE': [26, 26, 112],
            'MINT_CREAM': [245, 255, 250],
            'MISTY_ROSE': [255, 227, 224],
            'MOCCASIN': [255, 227, 181],
            'NAVAJO_WHITE': [255, 222, 173],
            'NAVY_BLUE': [0, 0, 128],
            'OLD_LACE': [252, 245, 230],
            'OLIVE': [128, 128, 0],
            'OLIVE_DRAB': [107, 143, 36],
            'ORANGE': [255, 166, 0],
            'ORANGE_RED': [255, 69, 0],
            'ORCHID': [217, 112, 214],
            'PALE_GOLDENROD': [237, 232, 171],
            'PALE_GREEN': [153, 250, 153],
            'PALE_TURQUOISE': [176, 237, 237],
            'PALE_VIOLET_RED': [219, 112, 148],
            'PAPAYA_WHIP': [255, 240, 214],
            'PEACH_PUFF': [255, 217, 186],
            'PERU': [204, 133, 64],
            'PINK': [255, 191, 204],
            'PLUM': [222, 161, 222],
            'POWDER_BLUE': [176, 224, 230],
            'PURPLE': [161, 33, 240],
            'WEB_PURPLE': [128, 0, 128],
            'REBECCA_PURPLE': [102, 51, 153],
            'ROSY_BROWN': [189, 143, 143],
            'ROYAL_BLUE': [64, 105, 224],
            'SADDLE_BROWN': [140, 69, 18],
            'SALMON': [250, 128, 115],
            'SANDY_BROWN': [245, 163, 97],
            'SEA_GREEN': [46, 140, 87],
            'SEASHELL': [255, 245, 237],
            'SIENNA': [161, 82, 46],
            'SILVER': [191, 191, 191],
            'SKY_BLUE': [135, 207, 235],
            'SLATE_BLUE': [107, 89, 204],
            'SLATE_GRAY': [112, 128, 143],
            'SNOW': [255, 250, 250],
            'SPRING_GREEN': [0, 255, 128],
            'STEEL_BLUE': [69, 130, 181],
            'TAN': [209, 181, 140],
            'TEAL': [0, 128, 128],
            'THISTLE': [217, 191, 217],
            'TOMATO': [255, 99, 71],
            'TURQUOISE': [64, 224, 209],
            'VIOLET': [237, 130, 237],
            'WHEAT': [245, 222, 178],
            'WHITE_SMOKE': [245, 245, 245],
            'YELLOW_GREEN': [153, 204, 51],
        }

        def __init__(self, conf):
            self.database = {}
            self.index = 1
            self.init_extended_colors()
            for key, style in conf.items():
                if isinstance(style, list):
                    colors, attr = self.translate(style)
                    curses.init_pair(self.index, *colors)
                    self.database[key] = curses.color_pair(self.index) | attr
                    self.index += 1

        def merge(self, conf):
            """Merges provides color/attribute styling config with existing mappings.
               and returns the merged result.
            """
            merged = dict(self.database)
            for key, style in conf.items():
                if isinstance(style, list):
                    colors, attr = self.translate(style)
                    curses.init_pair(self.index, *colors)
                    merged[key] = curses.color_pair(self.index) | attr
                    self.index += 1
                else:
                    merged[key] = conf[key]
            return merged

        def update(self, action):
            """Updates the given action configuration and replaces the color/attribute
               token list with a value suitable for use with addnstr(..).
            """
            for key in action:
                for trait in action[key]:
                    if isinstance(action[key][trait], list):
                        colors, attr = self.translate(action[key][trait])
                        curses.init_pair(self.index, *colors)
                        action[key][trait] = curses.color_pair(self.index) | attr
                        self.index += 1
            return action

        def translate(self, tokens):
            """Translates a list of color/attribute str tokens into the equivilent
               ncurses color/attribute values. Unrecognized tokens are mapped to zero.
               Returns two items: colors list, attribute
            """
            colors = [0, 0]
            attribute = 0
            for i in range(2):
                if i < len(tokens):
                    colors[i] = self.xlate_color_for.get(tokens[i], 0)
            if len(tokens) > 2:
                attribute = self.xlate_attr_for.get(tokens[2], 0)
            return colors, attribute

        def init_extended_colors(self):
            """Initialize extended (8+) colors with curses."""
            ndex = 1 + max(self.xlate_color_for.values())
            for color, rgb in self.x11_color_rgb.items():
                try:
                    curses.init_color(ndex, *rgb)
                except:
                    continue
                self.xlate_color_for[color] = ndex
                ndex += 1

        @classmethod
        def is_color(cls, token):
            """Verifies that a given string token is a recognized ncurses color."""
            return token in cls.xlate_color_for or token in cls.x11_color_rgb

        @classmethod
        def is_attr(cls, token):
            """Verifies that a given string token is a recognized ncurses attribute."""
            return token in cls.xlate_attr_for

        @classmethod
        def border_chrs(cls, names, mode='single'):
            """Returns the box-art characters for either double or single."""
            return {n: chr(cls.border_char_for[mode][n]) for n in names}

    class Worker(Thread):
        """The Worker threads will invoke the given generator function and load
           the Queue with its results.
        """
        def __init__(self, queue, generator, frequency):
            Thread.__init__(self)
            self.daemon    = True
            self.queue     = queue
            self.generator = generator
            self.frequency = float(frequency)
            self.stopped   = False
            self.paused    = False

        def run(self):
            """Text generator event loop populates the Queue."""
            while not self.stopped:
                if self.paused:
                    time.sleep(1)
                    continue
                if not self.queue.empty():
                    self.queue.get()
                self.queue.put(self.generator())
                time.sleep(self.frequency)
            self.queue.join()

        def stop(self):
            """Set the stopped flag to cause the run loop to exit."""
            self.stopped = True

        def toggle(self):
            """Set the paused flag to cause the run loop to do nothing."""
            self.paused = not self.paused

    class Tile:
        """The Tile represents a region on the terminal and maintains the
           text to be added.
        """
        def __init__(self, queue, **kwargs):
            self.lines      = []
            self.queue      = queue
            self.title      = kwargs['title']
            self.toggle_key = kwargs['toggle_key']
            self.geometry   = kwargs['geometry']
            self.styles     = kwargs['styles']
            self.action     = kwargs['action']
            self.memory     = None
            self.loaded     = False
            self.geometry['ypos'] = 0
            self.geometry['xpos'] = 0

        def __str__(self):
            return f'({self.title})' \
                   f'[{self.ypos}+{self.height},' \
                   f'{self.xpos}+{self.width}]'

        @property
        def has_border(self):
            """Boolean indicates border is on."""
            return self.styles['border']

        @property
        def height(self):
            """Provides the render height."""
            return self.geometry['height']

        @property
        def width(self):
            """Provides the render width."""
            return self.geometry['width']

        @property
        def ypos(self):
            """Provides the render ypos."""
            return self.geometry['ypos']

        @property
        def xpos(self):
            """Provides the render xpos."""
            return self.geometry['xpos']

        @property
        def visible(self):
            """Boolean indicates that Tile is currently enabled."""
            return self.memory is None

        def position(self, ypos, xpos):
            """Position the Tile at the given y/x coordinates."""
            if self.geometry['ypos'] != ypos or self.geometry['xpos'] != xpos:
                self.geometry['ypos'] = ypos
                self.geometry['xpos'] = xpos

        def markup_for(self, line_i, text):
            """Get the ncurses markup for the given text appearing on the
               given line number.
            """
            if len(text.strip()) == 0:
                return 0
            if line_i == 0 and \
               self.title is not None and \
               'title' in self.styles:
                return self.styles['title']
            keys = [p for p in self.styles if hasattr(p, 'search')]
            for key in keys:
                if re.search(key, text):
                    return self.styles[key]
            if 'body' in self.styles:
                return self.styles['body']
            return 0

        def load(self):
            """Load new lines from the queue."""
            if self.memory is not None:
                return None
            lines = []
            try:
                lines = self.queue.get_nowait()
            except EmptyQueue:
                return None
            self.loaded = True
            if len(lines) > 0:
                self.lines = []
                if self.title is not None:
                    self.lines.append(self.title)
                self.lines.extend(lines)
            if self.action is not None:
                for key, result in self.action.items():
                    if any(re.search(key, line) for line in self.lines):
                        return result
            return None

        def toggle(self, terminal):
            """Toggles the hidden/inactive state."""
            if self.loaded:
                if self.memory is None:
                    self.memory = self.lines
                    self.lines = [' '] * self.geometry['height']
                else:
                    self.lines = self.memory
                    self.memory = None
                    self.load()
                self.update(terminal)

        def draw_background(self, terminal, min_y, max_y, min_x, max_x_length):
            """Update the text on the ncurses terminal painting the background for this tile."""
            if self.has_border:
                char = CTiles.Stylist.border_chrs(['tl','horz','vert','tr','rtee','br','bl','ltee'])
                horizontal = char["horz"] * (max_x_length - 2)
                blank = " " * (max_x_length - 2)
                first_line = f'{char["tl"]}{horizontal}{char["tr"]}'
                title_line = f'{char["ltee"]}{horizontal}{char["rtee"]}'
                middle_line = f'{char["vert"]}{blank}{char["vert"]}'
                last_line = f'{char["bl"]}{horizontal}{char["br"]}'
                try:
                    terminal.addnstr(
                        min_y,
                        self.geometry['xpos'],
                        first_line,
                        max_x_length)
                    for line_i, line_y in enumerate(range(min_y + 1, max_y)):
                        line = title_line if line_i == 1 else middle_line
                        terminal.addnstr(
                            line_y,
                            self.geometry['xpos'],
                            line,
                            max_x_length)
                    terminal.addnstr(
                        max_y,
                        self.geometry['xpos'],
                        last_line,
                        max_x_length)
                except:
                    return False
            else:
                blank_line = " " * max_x_length
                try:
                    for line_y in range(min_y, max_y + 1):
                        terminal.addnstr(
                            line_y,
                            self.geometry['xpos'],
                            blank_line,
                            max_x_length)
                except:
                    return False
            return True

        def update(self, terminal):
            """Update the text on the ncurses terminal with the stored line data."""
            absolute_max_y, absolute_max_x = terminal.getmaxyx()
            absolute_max_y -= 3  # status bar
            absolute_max_x -= 1  # border

            min_y, min_x = self.geometry['ypos'], self.geometry['xpos']

            max_y = min(self.geometry['ypos'] + self.geometry['height'] - 1, absolute_max_y)
            max_x_length = min(self.geometry['width'], absolute_max_x - self.geometry['xpos'])

            if not self.draw_background(terminal, min_y, max_y, min_x, max_x_length):
                return

            line_i_offset = 0
            if self.has_border:
                min_y, min_x = min_y + 1, min_x + 1
                line_i_offset, border_cost = 0, 2
                max_y -= 1
                max_x_length -= 2

            if max_x_length == 0:
                return

            if min_y > max_y:
                return

            for line_i, line_y in enumerate(range(min_y, max_y + 1)):
                line = '.'
                if line_i == 1 and self.title is not None and self.has_border:
                    line_i_offset -= 1
                    continue
                line_i += line_i_offset
                if line_i < len(self.lines):
                    line = re.sub(r'\s', " ", self.lines[line_i])
                line += ' ' * (max_x_length - len(line))
                if line_i == 0 and \
                   self.memory is None and \
                   self.title is not None and \
                   self.toggle_key is not None and \
                   len(line) >= 3 + len(self.title):
                    line = line[0:-3] + f'[{self.toggle_key}]'
                args = [
                    line_y,
                    min_x,
                    line[0:max_x_length],
                    max_x_length,
                    self.markup_for(line_i, line)
                ]
                try:
                    terminal.addnstr(*args)
                except:
                    pass

    def __init__(self, config):
        if not self.is_valid_(config):
            raise AssertionError(f'Invalid {__class__.__name__} configuration')
        self.style = config['style']
        self.tiles = config['tiles']
        self.current_height = 0
        self.current_width = 0

    def screen_size_changed(self, terminal):
        """Determine if the terminal screen size has changed."""
        is_changed = False
        height, width = terminal.getmaxyx()
        if self.current_height != height or self.current_width != width:
            is_changed = True
            self.current_height = height
            self.current_width = width
        return is_changed

    @classmethod
    def valid_toggle_(cls, toggle):
        """Validate the 'toggle' configuration element."""
        if not isinstance(toggle, dict):
            print('toggle is not a dict', file=sys.stderr)
            return False
        result = True
        if 'key' in toggle and toggle['key'] is not None:
            if not isinstance(toggle['key'], str) or len(toggle['key']) != 1:
                print("toggle 'key' is not a one character str", file=sys.stderr)
                result = False
        if 'active' not in toggle:
            toggle['active'] = True
        elif not isinstance(toggle['active'], bool):
            print("toggle 'active' is not a bool", file=sys.stderr)
            result = False
        for field in toggle:
            if field not in ['key', 'active']:
                print(f'Invalid toggle field: {field}', file=sys.stderr)
                result = False
        return result

    @classmethod
    def valid_style_(cls, style):
        """Validate the 'style' configuration element."""
        result = True
        if 'border' not in style:
            style['border'] = False
        for field in style:
            if field not in ['background', 'border', 'title', 'body'] and \
                not hasattr(field, 'search'):
                print(f'Invalid style property: {field}', file=sys.stderr)
                result = False
            elif field == 'border':
                if not isinstance(style[field], bool):
                    print(f'Style property {field} must be a bool', file=sys.stderr)
                    result = False
            elif len(style[field]) < 2:
                print(f'{field} must have at least 2 colors', file=sys.stderr)
                result = False
            else:
                for ndex in range(2):
                    color = style[field][ndex]
                    if not cls.Stylist.is_color(color):
                        print(f'Invalid color: {color}', file=sys.stderr)
                        result = False
                if len(style[field]) > 2:
                    attr = style[field][2]
                    if not cls.Stylist.is_attr(attr):
                        print(f'Invalid attribute: {attr}', file=sys.stderr)
                        result = False
                if len(style[field]) > 3:
                    print(f'Too many color/attr: {field}', file=sys.stderr)
                    result = False
        return result

    @classmethod
    def valid_action_(cls, action):
        """Validate the 'style' configuration element."""
        if not isinstance(action, dict):
            print('action is not a dict', file=sys.stderr)
            return False
        result = True
        for pattern in action:
            if not hasattr(pattern, 'search'):
                print('action has non-re.Pattern key', file=sys.stderr)
                result = False
                continue
            if not isinstance(action[pattern], dict):
                print(f'action {pattern} is not a dict', file=sys.stderr)
                result = False
                continue
            for key in action[pattern]:
                if not isinstance(key, str):
                    print(f'action {pattern}: key is not str',
                            file=sys.stderr)
                    result = False
                    continue
                if key == 'background':
                    if not isinstance(action[pattern][key], list):
                        print(f'action {pattern} background must be a list',
                                file=sys.stderr)
                        result = False
                        continue
                    if len(action[pattern][key]) < 2:
                        print(f'action {pattern} '
                                'background must have at least 2 colors',
                                file=sys.stderr)
                        result = False
                        continue
                    for ndex in range(2):
                        color = action[pattern][key][ndex]
                        if not cls.Stylist.is_color(color):
                            print(f'Invalid color: {color}', file=sys.stderr)
                            result = False
                    if len(action[pattern][key]) > 2:
                        attr = action[pattern][key][2]
                        if not cls.Stylist.is_attr(attr):
                            print(f'Invalid attribute: {attr}', file=sys.stderr)
                            result = False
                    if len(action[pattern][key]) > 3:
                        print(f'Too many color/attr: {key}', file=sys.stderr)
                        result = False
                elif key == 'halt' or key == 'exit':
                    if not isinstance(action[pattern][key], bool):
                        print(f'action {pattern} {key} must be a boolean',
                                file=sys.stderr)
                        result = False
                else:
                    print(f'action {pattern} unrecognized key: {key}',
                            file=sys.stderr)
        return result

    def is_valid_(self, config):
        """Examine the configuration to verify it is valid."""
        if 'style' not in config:
            config['style'] = {}
        elif not isinstance(config['style'], dict):
            print("config 'style' must be a dict", file=sys.stderr)
            return False
        if 'tiles' not in config or not isinstance(config['tiles'], list):
            print("config 'tiles' must be a list", file=sys.stderr)
            return False
        result = True
        if not self.valid_style_(config['style']):
            result = False
        for ndex, tile in enumerate(config['tiles']):
            if not isinstance(tile, dict):
                print(f'tile {ndex} is not a dict', file=sys.stderr)
                result = False
                continue
            if 'title' not in tile:
                config['tiles'][ndex]['title'] = None
                tile = config['tiles'][ndex]
            if 'toggle' not in tile:
                config['tiles'][ndex]['toggle'] = {'key': None, 'active': True}
                tile = config['tiles'][ndex]
            if 'frequency' not in tile:
                config['tiles'][ndex]['frequency'] = 1.0
                tile = config['tiles'][ndex]
            if 'style' not in tile:
                config['tiles'][ndex]['style'] = {}
                tile = config['tiles'][ndex]
            if 'action' not in tile:
                config['tiles'][ndex]['action'] = {}
                tile = config['tiles'][ndex]
            if tile['title'] is not None and not isinstance(tile['title'], str):
                print(f'tile {ndex} title is not a str', file=sys.stderr)
                result = False
            if not isinstance(tile['frequency'], float):
                print(f'tile {ndex} frequency is not a float', file=sys.stderr)
                result = False
            if not self.valid_toggle_(tile['toggle']):
                print(f'tile {ndex} has invalid toggle', file=sys.stderr)
                result = False
            if not self.valid_style_(tile['style']):
                print(f'tile {ndex} has invalid style', file=sys.stderr)
                result = False
            if not self.valid_action_(tile['action']):
                print(f'tile {ndex} has invalid action', file=sys.stderr)
                result = False

            for field in tile:
                if field not in ['title', 'toggle', 'frequency',
                                 'style', 'generator', 'geometry', 'action']:
                    print(f'Invalid tile {ndex} field: {field}', file=sys.stderr)
                    result = False
        return result

    def draw_background(self, terminal):
        height, width = terminal.getmaxyx()
        if self.style['border']:
            char = CTiles.Stylist.border_chrs(['horz','vert', 'tl','tr','br','bl'], 'double')
            first_line = char['tl'] + (char['horz'] * (width - 2)) + char['tr']
            middle_line = char['vert'] + (" " * (width - 2)) + char['vert']
            last_line = char['bl'] + (char['horz'] * (width - 2)) + char['br']
            terminal.addnstr(0, 0, first_line, len(first_line))
            for line_y in range(1, height - 2):
                terminal.addnstr(line_y, 0, middle_line, width)
            terminal.addnstr(height - 2, 0, last_line, len(last_line))
            terminal.addnstr(height - 1, 0, " " * (width - 1), width - 1)
        else:
            blank_line = " " * width
            for line_y in range(height - 1):
                terminal.addnstr(line_y, 0, blank_line, width)
            terminal.addnstr(height - 1, 0, blank_line, width - 1)


    def arrange(self, terminal, slabs):
        """Update the xpos/ypos attributes of the Tiles
           to arrange them on the screen.
        """
        height, width = terminal.getmaxyx()
        grid = self.Grid(height, width, self.style['border'])
        for slab in [p for p in slabs if p.visible]:
            slab.toggle(terminal)
            location = grid.search(slab)
            if location is None:
                continue
            slab.position(location['ypos'], location['xpos'])
            slab.toggle(terminal)
            grid.reserve(slab)

    def __call__(self, terminal):

        queues, workers, slabs, togglers = [], [], [], {}

        stylist = self.Stylist(self.style)

        for tile in self.tiles:

            queues.append(Queue(1))

            workers.append(self.Worker(queues[-1],
                                       generator = tile['generator'],
                                       frequency = tile['frequency']))

            slabs.append(self.Tile(queues[-1],
                                   title      = tile['title'],
                                   geometry   = tile['geometry'],
                                   toggle_key = tile['toggle']['key'],
                                   styles     = stylist.merge(tile['style']),
                                   action     = stylist.update(tile['action'])))

            if tile['toggle']['key'] is not None:
                togglers[ord(tile['toggle']['key'])] = len(slabs) - 1

        for worker in workers:
            worker.start()

        curses.noecho()
        curses.cbreak()
        curses.curs_set(0)
        if curses.has_colors():
            curses.start_color()
            if 'background' in stylist.database:
                terminal.bkgd(stylist.database['background'])
            else:
                curses.use_default_colors()

        terminal.clear()
        terminal.nodelay(1)

        paused = False
        self.draw_background(terminal)
        self.arrange(terminal, slabs)
        try:
            while True:
                if not paused:
                    for slab in slabs:
                        action = slab.load()
                        if action is not None:
                            if 'background' in action:
                                terminal.bkgd(action['background'])
                            if 'halt' in action:
                                paused = True
                            if 'exit' in action:
                                break
                    for slab in slabs:
                        slab.update(terminal)
                    if self.screen_size_changed(terminal):
                        self.draw_background(terminal)
                        self.arrange(terminal, slabs)
                        terminal.bkgd(stylist.database['background'])
                    terminal.refresh()
                key_char = terminal.getch()
                if key_char == -1:
                    continue
                if key_char == self.Command.QUIT:
                    break
                if key_char == self.Command.TOGGLE_HALT:
                    if paused:
                        paused = False
                        terminal.bkgd(stylist.database['background'])
                    else:
                        paused = True
                    continue
                if not paused:
                    if key_char in togglers:
                        ndex = togglers[key_char]
                        workers[ndex].toggle()
                        slabs[ndex].toggle(terminal)
                        self.draw_background(terminal)
                        self.arrange(terminal, slabs)
                        terminal.bkgd(stylist.database['background'])
        except KeyboardInterrupt:
            return
        finally:
            for worker in workers:
                worker.stop()

    def run(self):
        """The run method simply invokes curses.wrapper."""
        wrapper(self)
