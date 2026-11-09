# Dedicated migration input recipe. Building is a separate authorized operation.
FROM docker.io/library/python@sha256:1aaa65a85fda306ffb8b910824d4e93bdce61e212c7e87168123ea3073b41a1a AS build
WORKDIR /build
COPY wheels/ /wheels/
COPY requirements.txt requirements-linux-cp312.lock offline-python-wheelhouse.json /build/
COPY offline_python_wheelhouse.py /build/offline_python_wheelhouse.py
RUN --network=none PIP_CONFIG_FILE=/dev/null python -I /build/offline_python_wheelhouse.py verify \
      --requirements /build/requirements.txt --manifest /build/offline-python-wheelhouse.json \
      --lock /build/requirements-linux-cp312.lock --wheelhouse /wheels \
    && PIP_CONFIG_FILE=/dev/null python -I -m pip --isolated install \
      --no-index --find-links /wheels --require-hashes --only-binary=:all: \
      --no-cache-dir --disable-pip-version-check --no-input -r /build/requirements-linux-cp312.lock \
    && python -I -m pip check
FROM docker.io/library/python@sha256:1aaa65a85fda306ffb8b910824d4e93bdce61e212c7e87168123ea3073b41a1a
ARG SOURCE_COMMIT
LABEL org.opencontainers.image.revision=$SOURCE_COMMIT
WORKDIR /app
COPY --from=build /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY app/ /app/app/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/alembic.ini
USER 65532:65532
# No migration or application is started by this image's default command.
ENTRYPOINT ["/bin/false"]
CMD []
