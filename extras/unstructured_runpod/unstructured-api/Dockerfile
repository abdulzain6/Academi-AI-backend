FROM downloads.unstructured.io/unstructured-io/unstructured:latest as base

# NOTE: NB_USER ARG for mybinder.org compat:
#       https://mybinder.readthedocs.io/en/latest/tutorials/dockerfile.html

# Copy necessary files
COPY requirements.txt requirements.txt

RUN pip install -r requirements.txt

# Use start.sh as the entry point
COPY rp_handler.py rp_handler.py
COPY rp_schema.py rp_schema.py
#COPY test_input.json test_input.json

CMD python3 -u rp_handler.py
