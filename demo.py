#!/usr/bin/env python3
"""
Demonstration program using the CTiles ncurses interface.

Author: Dylan Doxey
Data: Feb 22, 2023
See: https://github.com/ddoxey/curtiles
"""
import re
import textwrap
import datetime
import subprocess
from curtiles import CTiles

StartTime = datetime.datetime.now()

def shell_command(cmd_tokens):
    proc = subprocess.run(cmd_tokens,
                    encoding='UTF-8',
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    check=False)
    result = {
        'status': proc.returncode,
        'stdout': proc.stdout,
        'stderr': proc.stderr
    }
    return result

def make_header():
    runtime = datetime.datetime.now() - StartTime
    return [f'Runtime: {runtime}']

def make_calendar():
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cal = shell_command(['cal'])
    lines = [f' {timestamp} ']
    lines.extend(cal['stdout'].split("\n"))
    return lines

def make_platform():
    uname = shell_command(['uname', '-s', '-r', '-m', '-p', '-i', '-o'])
    return uname['stdout'].split(" ")


def make_proc_list():
    proc_table = shell_command(['ps', '-e'])
    return proc_table['stdout'].split("\n")


def make_active_users():
    who = shell_command(['who'])
    return who['stdout'].split("\n")


def make_fortune():
    fort = shell_command(['fortune'])
    lines = [l for l in fort['stdout'].split("\n") if len(l) > 0]
    signature = None
    if len(lines) > 1 and re.match(r'^\s+[-]', lines[-1]):
        signature = textwrap.wrap(lines.pop(), width=55)
        lines = textwrap.wrap(" ".join(lines), width=55)
        lines.extend(signature)
    else:
        lines = textwrap.wrap(" ".join(lines), width=55)
    return lines


if __name__ == '__main__':
    conf = {
        'style': {
            'background': ['WHITE', 'BLUE'],
            'title': ['BLUE', 'WHITE'],
        },
        'tiles': [
            {
                'toggle': { 'key': 'h' },
                'generator': make_header,
                'geometry': {'height': 2, 'width': 128},
                'frequency': 0.25,
                'style': {
                    re.compile(r'[:]0[0-9][.]'): ['MAGENTA', 'BLACK', 'BOLD'],
                },
                'action': {
                    re.compile(r'[:]10[.]'): {
                        'background': ['WHITE', 'LIME'],
                        'halt': True,
                    }
                }
            },
            {
                'title': 'CALENDAR',
                'toggle': { 'key': 'c' },
                'generator': make_calendar,
                'geometry': {'height': 15, 'width': 24},
                'frequency': 0.25,
                'style': {
                    'title': ['WHITE', 'RED', 'BOLD'],
                },
            },
            {
                'title': 'PLATFORM',
                'toggle': { 'key': 'l' },
                'generator': make_platform,
                'geometry': {'height': 10, 'width': 24},
                'frequency': 60.0,
            },
            {
                'title': 'PROCESSES',
                'toggle': { 'key': 'p' },
                'generator': make_proc_list,
                'geometry': {'height': 20, 'width': 36},
                'frequency': 0.25,
                'style': {
                    re.compile(r'00[:]00[:]00'): ['BLACK', 'YELLOW', 'BOLD'],
                },
            },
            {
                'title': 'ACTIVE USERS',
                'toggle': { 'key': 'u' },
                'generator': make_active_users,
                'geometry': {'height': 20, 'width': 56},
                'frequency': 0.25,
                'style': {
                    'title': ['WHITE', 'FUCHSIA'],
                },
            },
            {
                'title': 'FORTUNE',
                'toggle': { 'key': 'f', 'active': False },
                'generator': make_fortune,
                'geometry': {'height': 5, 'width': 56},
                'frequency': 60.0,
            },
        ]
    }
    ui = CTiles(conf)
    ui.run()
