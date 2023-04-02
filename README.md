# curtiles
The *curtiles* module is designed to provide an **ncurses** tiling framework for Python. The `CTiles` class handles all of the complexity around updating screen text, automatic layout, refreshing on resize, and any of the quirks around interracting with the underlying **ncurses** interfaces.

## Demo
The inluded `demo.py` program illustrates an example `CTiles` application which calls system utilities to provide a dynamic "dashboard" style user experience.

<img width="898" alt="demo" src="https://user-images.githubusercontent.com/2474931/229372634-caf7fbcc-ca24-4b37-90e1-748a1a789899.png">

## Usage:

```python
#!/usr/bin/env python3
import datetime
from curtiles import CTiles

def time_of_day():
    now = datetime.datetime.now()
    return [now.strftime("%Y-%m-%d %H:%M:%S")]


if __name__ == '__main__':
    conf = {
        'style': {
            'background': ['WHITE', 'BLUE']
        },
        'tiles': [
            {
                'title': 'TODAY',
                'generator': time_of_day,
                'geometry': {'height': 11, 'width': 22},
                'frequency': 1.0,
            }
        ]
    }
    ui = CTiles(conf)
    ui.run()
```

This sample program demonstrates `CTiles` program with one tile that displays the current time, with bold white text on a blue background.
The `CTiles` constructor accepts a dict with a `style` key and a `tiles` key.
