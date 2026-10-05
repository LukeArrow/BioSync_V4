ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:3.21
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-pip \
    && python3 -m venv /opt/venv

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /opt/biosync
COPY rootfs/ /
RUN pip install --no-cache-dir -r requirements.txt

COPY run.sh /run.sh
RUN chmod +x /run.sh

ARG BUILD_VERSION
ARG BUILD_ARCH
LABEL io.hass.version="${BUILD_VERSION}" \
      io.hass.type="addon" \
      io.hass.arch="${BUILD_ARCH}"

CMD ["/run.sh"]
