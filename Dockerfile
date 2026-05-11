FROM ghcr.io/ad-sdl/madsci:latest

# Install hardware-specific libraries required by real device interfaces.
# Must install into the MADSci virtualenv (/home/madsci/MADSci/.venv)
# which is used at runtime by the madsci-entrypoint.sh.
COPY devices/requirements.txt /tmp/device-requirements.txt
RUN uv pip install --python /home/madsci/MADSci/.venv/bin/python \
    -r /tmp/device-requirements.txt && \
    rm /tmp/device-requirements.txt
