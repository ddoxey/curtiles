#!/usr/bin/env python3
"""
Demonstration program for using X11 colors with CTiles.

Author: Dylan Doxey
Data: Mar 16, 2023
See: https://github.com/ddoxey/curtiles
"""
from curtiles import CTiles

def make_space():
    return [' ']

color_names = []
color_names.extend(CTiles.Stylist.xlate_color_for.keys())
color_names.extend(CTiles.Stylist.x11_color_rgb.keys())

tiles = []

for bg in ['WHITE', 'THISTLE']:
    for color_name in color_names:
        tiles.append({
            'title': color_name,
            'generator': make_space,
            'geometry': {'height': 1, 'width': len(color_name)},
            'style': {
                'title': [color_name, bg, 'BOLD']
            }
        })


if __name__ == '__main__':
    conf = {
        'style': {
            'background': ['THISTLE', 'THISTLE'],
        },
        'tiles': tiles,
    }
    ui = CTiles(conf)
    ui.run()
