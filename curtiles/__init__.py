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
from queue import Queue, Empty as EmptyQueue
from curses import wrapper
from threading import Thread


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

    class Stylist:
        """The Stylist initializes the styling pairs in the curses environment
           and provides a style database for later reference.
        """
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

        def __init__(self, conf):
            self.database = {}
            self.index = 1
            for key, style in conf.items():
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
                colors, attr = self.translate(style)
                curses.init_pair(self.index, *colors)
                merged[key] = curses.color_pair(self.index) | attr
                self.index += 1
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

        @classmethod
        def is_color(cls, token):
            """Verifies that a given string token is a recognized ncurses color."""
            return token in cls.xlate_color_for

        @classmethod
        def is_attr(cls, token):
            """Verifies that a given string token is a recognized ncurses attribute."""
            return token in cls.xlate_attr_for

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

        def run(self):
            """Text generator event loop populates the Queue."""
            while not self.stopped:
                if not self.queue.empty():
                    self.queue.get()
                self.queue.put(self.generator())
                time.sleep(self.frequency)
            self.queue.join()

        def stop(self):
            """Set the stopped flag to cause the run loop to exit."""
            self.stopped = True

    class Panel:
        """The Panel represents a region on the terminal and maintains the
           text to be added.
        """
        def __init__(self, queue, **kwargs):
            self.lines    = []
            self.queue    = queue
            self.title    = kwargs['title']
            self.geometry = kwargs['geometry']
            self.styles   = kwargs['styles']
            self.action   = kwargs['action']

        def markup_for(self, line_i, text):
            """Get the ncurses markup for the given text appearing on the given line number."""
            if line_i == 0 and \
               self.title is not None and \
               'title' in self.styles:
                return self.styles['title']
            keys = [p for p in self.styles if isinstance(p, re.Pattern)]
            for key in keys:
                if re.search(key, text):
                    return self.styles[key]
            return 0

        def load(self):
            """Load new lines from the queue."""
            lines = []
            try:
                lines = self.queue.get_nowait()
            except EmptyQueue:
                return None
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

        def update(self, terminal):
            """Update the text on the ncurses terminal with the stored line data."""
            max_y, max_x = terminal.getmaxyx()
            max_y_offset = min(self.geometry['ypos'] + self.geometry['height'],
                               max_y - self.geometry['ypos'])
            max_x_length = min(self.geometry['width'],
                               max_x - self.geometry['xpos'])
            if max_y_offset > 0 and max_x_length > 0:
                for y_offset in range(self.geometry['height']):
                    if y_offset > max_y_offset:
                        break
                    line = ' '
                    if y_offset < len(self.lines):
                        line = re.sub(r'\s', " ", self.lines[y_offset])
                    if len(line) < max_x_length:
                        line += ' ' * (max_x_length - len(line))
                    terminal.addnstr(
                        self.geometry['ypos'] + y_offset,
                        self.geometry['xpos'],
                        line[0:max_x_length],
                        max_x_length,
                        self.markup_for(y_offset, line))

    def __init__(self, config):
        if not self.is_valid_(config):
            raise AssertionError(f'Invalid {__class__.__name__} configuration')
        self.style = config['style']
        self.tiles = config['tiles']

    @classmethod
    def valid_style_(cls, style):
        """Validate the 'style' configuration element."""
        result = True
        for field in style:
            if field not in ['background', 'title'] and \
                not isinstance(field, re.Pattern):
                print(f'Invalid style property: {field}', file=sys.stderr)
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
            if not isinstance(pattern, re.Pattern):
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
                elif key == 'halt':
                    if not isinstance(action[pattern][key], bool):
                        print(f'action {pattern} halt must be a boolean',
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
            if not self.valid_style_(tile['style']):
                print(f'tile {ndex} has invalid style', file=sys.stderr)
                result = False
            if not self.valid_action_(tile['action']):
                print(f'tile {ndex} has invalid action', file=sys.stderr)
                result = False

            for field in tile:
                if field not in ['title', 'frequency',
                                 'style', 'generator', 'geometry', 'action']:
                    print(f'Invalid tile {ndex} field: {field}', file=sys.stderr)
                    result = False
        return result

    def __call__(self, terminal):

        queues, workers, panels = [], [], []

        stylist = self.Stylist(self.style)

        for tile in self.tiles:

            queues.append(Queue(1))

            workers.append(self.Worker(queues[-1],
                                       generator = tile['generator'],
                                       frequency = tile['frequency']))

            panels.append(self.Panel(queues[-1],
                                     title    = tile['title'],
                                     geometry = tile['geometry'],
                                     styles   = stylist.merge(tile['style']),
                                     action   = stylist.update(tile['action'])))

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

        try:
            paused = False
            while True:
                if not paused:
                    for panel in panels:
                        action = panel.load()
                        if action is not None:
                            if 'background' in action:
                                terminal.bkgd(action['background'])
                            if 'halt' in action:
                                paused = True
                    for panel in panels:
                        panel.update(terminal)
                    terminal.refresh()
                key_char = terminal.getch()
                if key_char == self.Command.QUIT:
                    break
                if key_char == self.Command.TOGGLE_HALT:
                    if paused:
                        paused = False
                        terminal.bkgd(stylist.database['background'])
                    else:
                        paused = True
        except KeyboardInterrupt:
            return
        finally:
            for worker in workers:
                worker.stop()

    def run(self):
        """The run method simply invokes curses.wrapper."""
        wrapper(self)
