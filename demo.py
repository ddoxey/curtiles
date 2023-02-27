#!/usr/bin/env python3
import re
import time
import random
import textwrap
import datetime
import subprocess
from curtiles import CTiles

StartTime = datetime.datetime.now()

def shell_command(cmd_tokens):
    p = subprocess.run(cmd_tokens,
                    encoding='UTF-8',
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT)
    result = {
        'status': p.returncode,
        'stdout': p.stdout,
        'stderr': p.stderr
    }
    return result

def make_header():
    runtime = datetime.datetime.now() - StartTime
    return [f'Runtime: {runtime}']

def make_calendar():
    day = datetime.datetime.now().strftime("%d")
    dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cal = shell_command(['cal'])
    lines = [f' {dt} ']
    lines.extend(cal['stdout'].split("\n"))
    return lines

def make_platform():
    ps = shell_command(['uname', '-s', '-r', '-m', '-p', '-i', '-o'])
    return ps['stdout'].split(" ")


def make_proc_list():
    ps = shell_command(['ps', '-e'])
    return ps['stdout'].split("\n")


def make_active_users():
    ps = shell_command(['who'])
    return ps['stdout'].split("\n")


def make_fortune():
    ps = shell_command(['fortune'])
    lines = [l for l in ps['stdout'].split("\n") if len(l) > 0]
    signature = None
    if len(lines) > 1 and re.match(r'^\s+[-]', lines[-1]):
        signature = textwrap.wrap(lines.pop(), width=55)
        lines = textwrap.wrap(" ".join(lines), width=55)
        lines.extend(signature)
    else:
        lines = textwrap.wrap(" ".join(lines), width=55)
    return lines


if __name__ == '__main__':
    conf = [
        {
            'generator': make_header,
            'geometry': {'height': 3, 'width': 45, 'ypos': 0, 'xpos': 0},
            'frequency': 0.25,
        },
        {
            'title': 'CALENDAR',
            'generator': make_calendar,
            'geometry': {'height': 15, 'width': 24, 'ypos': 2, 'xpos': 0},
            'frequency': 0.25,
        },
        {
            'title': 'PLATFORM',
            'generator': make_platform,
            'geometry': {'height': 10, 'width': 24, 'ypos': 12, 'xpos': 0},
            'frequency': 60.0,
        },
        {
            'title': 'PROCESSES',
            'generator': make_proc_list,
            'geometry': {'height': 20, 'width': 36, 'ypos': 2, 'xpos': 25},
            'frequency': 0.25,
        },
        {
            'title': 'ACTIVE USERS',
            'generator': make_active_users,
            'geometry': {'height': 20, 'width': 56, 'ypos': 2, 'xpos': 64},
            'frequency': 0.25,
        },
        {
            'title': 'FORTUNE',
            'generator': make_fortune,
            'geometry': {'height': 5, 'width': 56, 'ypos': 25, 'xpos': 1},
            'frequency': 60.0,
        },
    ]
    ui = CTiles(conf)
    ui.run()
