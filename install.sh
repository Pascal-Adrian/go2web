#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Install the package
pip3 install --upgrade pip
pip3 install -e "$SCRIPT_DIR"

echo "go2web has been installed successfully!"
echo "You can now use go2web from any directory."