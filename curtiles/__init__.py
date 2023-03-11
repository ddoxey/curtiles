import re
import sys
import time
import curses
import datetime
from queue import Queue
from curses import wrapper
from threading import Thread


class CTiles:

    class Command:
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
            self.db = {}
            self.index = 1
            for key, style in conf.items():
                colors, attr = self.translate(style)
                curses.init_pair(self.index, *colors)
                self.db[key] = curses.color_pair(self.index) | attr
                self.index += 1

        def merge(self, conf):
            merged = dict(self.db)
            for key, style in conf.items():
                colors, attr = self.translate(style)
                curses.init_pair(self.index, *colors)
                merged[key] = curses.color_pair(self.index) | attr
                self.index += 1
            return merged

        def update(self, action):
            for key in action:
                for trait in action[key]:
                    if isinstance(action[key][trait], list):
                        colors, attr = self.translate(action[key][trait])
                        curses.init_pair(self.index, *colors)
                        action[key][trait] = curses.color_pair(self.index) | attr
                        self.index += 1
            return action

        def translate(self, tokens):
            colors = [0, 0]
            attribute = 0
            for i in range(2):
                if i < len(tokens):
                    colors[i] = self.xlate_color_for.get(tokens[i], 0)
            if len(tokens) > 2:
                attribute = self.xlate_attr_for.get(tokens[2], 0)
            return colors, attribute

        @classmethod
        def is_color(self, token):
            return token in self.xlate_color_for

        @classmethod
        def is_attr(self, token):
            return token in self.xlate_attr_for

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
                try:
                    if not self.queue.empty():
                        self.queue.get()
                except Exception:
                    return
                self.queue.put(self.generator())
                time.sleep(self.frequency)
            self.queue.join()

        def stop(self):
            self.stopped = True

    class Panel:
        """The Panel represents a region on the terminal and maintains the
           text to be added.
        """
        def __init__(self, queue, **kwargs):
            self.lines  = []
            self.queue  = queue
            self.title  = kwargs['title']
            self.height = kwargs['geometry']['height']
            self.width  = kwargs['geometry']['width']
            self.ypos   = kwargs['geometry']['ypos']
            self.xpos   = kwargs['geometry']['xpos']
            self.styles = kwargs['styles']
            self.action = kwargs['action']

        def markup_for(self, line_i, text):
            if line_i == 0 and \
               self.title is not None and \
               'title' in self.styles:
                return self.styles['title']
            else:
                keys = [p for p in self.styles if isinstance(p, re.Pattern)]
                for key in keys:
                    if re.search(key, text):
                        return self.styles[key]
            return 0

        def load(self):
            lines = []
            try:
                lines = self.queue.get_nowait()
            except Exception:
                return
            if len(lines):
                self.lines = []
                if self.title is not None:
                    self.lines.append(self.title)
                self.lines.extend(lines)
            if self.action is not None:
                for key, result in self.action.items():
                    if any([re.search(key, line) for line in self.lines]):
                        return result
            return None

        def update(self, terminal):
            max_y, max_x = terminal.getmaxyx()
            max_y_offset = min(self.ypos + self.height, max_y - self.ypos)
            max_x_length = min(self.width, max_x - self.xpos)
            if max_y_offset > 0 and max_x_length > 0:
                for y_offset in range(self.height):
                    if y_offset > max_y_offset:
                        break
                    line = ' '
                    if y_offset < len(self.lines):
                        line = re.sub(r'\s', " ", self.lines[y_offset])
                    if len(line) < max_x_length:
                        line += ' ' * (max_x_length - len(line))
                    try:
                        terminal.addnstr(
                            self.ypos + y_offset,
                            self.xpos,
                            line[0:max_x_length],
                            max_x_length,
                            self.markup_for(y_offset, line))
                    except:
                        pass

    def __init__(self, config):
        if not self.is_valid_(config):
            raise Exception(f'Invalid {__class__.__name__} configuration')
        self.style = config['style']
        self.tiles = config['tiles']

    def is_valid_(self, config):
        if 'style' not in config:
            config['style'] = {}
        elif not isinstance(config['style'], dict):
            print("config 'style' must be a dict", file=sys.stderr)
            return False
        if 'tiles' not in config or not isinstance(config['tiles'], list):
            print("config 'tiles' must be a list", file=sys.stderr)
            return False
        def valid_style_(style):
            result = True
            for field in style:
                if field not in ['background', 'title'] and \
                   not isinstance(field, re.Pattern):
                    print(f'Invalid style property: {field}', file=sys.stderr)
                    result = False
                else:
                    for n in range(2):
                        color = style[field][n]
                        if not self.Stylist.is_color(color):
                            print(f'Invalid color: {color}', file=sys.stderr)
                            result = False
                    if len(style[field]) > 2:
                        attr = style[field][2]
                        if not self.Stylist.is_attr(attr):
                            print(f'Invalid attribute: {attr}', file=sys.stderr)
                            result = False
                    if len(style[field]) > 3:
                        print(f'Too many color/attr: {field}', file=sys.stderr)
                        result = False
            return result
        result = True
        if not valid_style_(config['style']):
            result = False
        for n, tile in enumerate(config['tiles']):
            if not isinstance(tile, dict):
                print(f'tile {n} is not a dict', file=sys.stderr)
                result = False
                continue
            if 'title' not in tile:
                config['tiles'][n]['title'] = None
                tile = config['tiles'][n]
            if 'frequency' not in tile:
                config['tiles'][n]['frequency'] = 1.0
                tile = config['tiles'][n]
            if 'style' not in tile:
                config['tiles'][n]['style'] = {}
                tile = config['tiles'][n]
            if 'action' not in tile:
                config['tiles'][n]['action'] = {}
                tile = config['tiles'][n]
            if tile['title'] is not None and not isinstance(tile['title'], str):
                print(f'tile {n} title is not a str', file=sys.stderr)
                result = False
            if not isinstance(tile['action'], dict):
                print(f'tile {n} action is not a dict', file=sys.stderr)
                result = False
            if not isinstance(tile['frequency'], float):
                print(f'tile {n} frequency is not a float', file=sys.stderr)
                result = False
            if not valid_style_(tile['style']):
                print(f'tile {n} has invalid style', file=sys.stderr)
                result = False
            for field in tile:
                if field not in ['title', 'frequency',
                                 'style', 'generator', 'geometry', 'action']:
                    print(f'Invalid tile {n} field: {field}', file=sys.stderr)
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

        try:
            curses.noecho()
            curses.cbreak()
            curses.curs_set(0)
            if curses.has_colors():
                curses.start_color()
                if 'background' in stylist.db:
                    terminal.bkgd(stylist.db['background'])
                else:
                    curses.use_default_colors()
        except Exception:
            pass

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
                elif key_char == self.Command.TOGGLE_HALT:
                    if paused:
                        paused = False
                        terminal.bkgd(stylist.db['background'])
                    else:
                        paused = True
        except(KeyboardInterrupt):
            return
        finally:
            for worker in workers:
                worker.stop()

    def run(self):
        wrapper(self)
