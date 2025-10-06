#!/bin/bash

# python setup
pip install uv --break-system-packages
uv sync
source .venv/bin/activate
echo "export PATH=$PATH" >> ~/.bashrc
