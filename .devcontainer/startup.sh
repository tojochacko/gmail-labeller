#!/bin/bash

# python setup
pushd 
pip install uv --break-system-packages
uv init
uv sync
source .venv/bin/activate
echo "export PATH=$PATH" >> ~/.bashrc
popd
