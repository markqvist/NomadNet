FROM python:3.11-rc-alpine3.14 as build

RUN apk add --no-cache build-base linux-headers libffi-dev cargo

# Create a virtualenv that we'll copy to the published image
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip3 install setuptools-rust pyopenssl cryptography

COPY . /app/
RUN cd /app/ && python3 setup.py install

# Use multi-stage build, as we don't need rust compilation on the final image
FROM python:3.11-rc-alpine3.14

LABEL org.opencontainers.image.documentation="https://github.com/markqvist/NomadNet#nomad-network-daemon-with-docker"

ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED="yes"
COPY --from=build /opt/venv /opt/venv

VOLUME /root/.reticulum
VOLUME /root/.nomadnetwork

ENTRYPOINT ["nomadnet"]
CMD ["--daemon"]
