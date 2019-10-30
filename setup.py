"""setup.py - install script for the MCC."""

import re
import io

from setuptools import setup

setup(
    name='mcc',
    version='_dev_',

    author='Johannes Schlatow',
    author_email='schlatow@ida.ing.tu-bs.de',
    description='Multi-Change Controller',

    install_requires=['xdot', 'networkx', 'ortools'],

    py_modules=['mcc'],
)
