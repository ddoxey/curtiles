import re
import time
import curses
import datetime
from curses import wrapper
from threading import Thread
from multiprocessing import Queue


class CTiles:

    class Style:
        HEADER = 1

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

        def run(self):
            """Text generator event loop populates the Queue."""
            while True:
                try:
                    if not self.queue.empty():
                        self.queue.get()
                except Exception:
                    return
                self.queue.put(self.generator())
                time.sleep(self.frequency)

    class Panel:
        """The Panel represents a region on the terminal and maintains the
           text to be added.
        """
        def __init__(self, queue, **kwargs):
            self.lines  = []
            self.queue  = queue
            self.title  = kwargs['title'] if 'title' in kwargs else None
            self.height = kwargs['geometry']['height']
            self.width  = kwargs['geometry']['width']
            self.ypos   = kwargs['geometry']['ypos']
            self.xpos   = kwargs['geometry']['xpos']

        def markup_for(self, line_i, text):
            if line_i == 0 and self.title is not None:
                return curses.color_pair(CTiles.Style.HEADER)
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

    def __init__(self, configs):
        self.configs = configs

    def __call__(self, terminal):

        queues, workers, panels = [], [], []

        for config in self.configs:

            if 'title' not in config:
                config['title'] = None

            if 'frequency' not in config:
                config['frequency'] = 1.0

            queues.append(Queue(1))

            workers.append(self.Worker(queues[-1],
                                       generator = config['generator'],
                                       frequency = config['frequency']))

            panels.append(self.Panel(queues[-1],
                                     title    = config['title'],
                                     geometry = config['geometry']))

        for worker in workers:
            worker.start()

        try:
            curses.noecho()
            curses.cbreak()
            curses.curs_set(0)
            if curses.has_colors():
                curses.start_color()
                curses.use_default_colors()
                curses.init_pair(CTiles.Style.HEADER, curses.COLOR_BLUE, -1)
        except Exception:
            pass

        terminal.clear()

        try:
            while True:
                for panel in panels:
                    panel.load()
                for panel in panels:
                    panel.update(terminal)
                terminal.refresh()
        except(KeyboardInterrupt):
            for queue in queues:
                queue.close()
            for worker in workers:
                worker.join()

    def run(self):
        wrapper(self)
