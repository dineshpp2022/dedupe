#!/bin/bash

# Install pip manually
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python3 get-pip.py

# Install dependencies
pip install -r requirements.txt

# Start Streamlit
streamlit run "Ask about contacts - Dataverse.py" --server.port=8000 --server.address=0.0.0.0