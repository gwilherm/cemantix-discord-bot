#!/bin/bash

if [ ! -f "token.sh" ]
then
    echo "Missing discord token."
    echo "Pease run the make command before."
    exit 1
fi

source token.sh

source ./venv/bin/activate
python3 main.py