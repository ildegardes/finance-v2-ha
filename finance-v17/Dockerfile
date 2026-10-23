FROM python:3.12.7-slim-bookworm@sha256:60d9996b6a8a3689d36db740b49f4327be3be09a21122bd02fb8895abb38b50d
LABEL io.hass.version="0.1.22-open-finance.1" \
      io.hass.type="app" \
      io.hass.arch="aarch64|amd64"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/finance-v2/src
WORKDIR /opt/finance-v2
COPY requirements-deploy.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check --only-binary=:all: --require-hashes --requirement requirements-deploy.txt \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin financev2
COPY --chown=financev2:financev2 src ./src
COPY --chown=financev2:financev2 migrations ./migrations
COPY --chown=financev2:financev2 run.sh ./run.sh
COPY --chown=financev2:financev2 migrate.sh ./migrate.sh
RUN chmod 0755 /opt/finance-v2/run.sh /opt/finance-v2/migrate.sh
EXPOSE 8766
ENTRYPOINT ["/opt/finance-v2/run.sh"]
