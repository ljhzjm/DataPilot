FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg

RUN groupadd --gid 10001 sandbox \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin sandbox \
    && pip install --no-cache-dir \
        matplotlib==3.10.0 \
        numpy==2.2.1 \
        pandas==2.2.3 \
        pyarrow==19.0.0

COPY runner.py /opt/sandbox/runner.py

USER 10001:10001
WORKDIR /workspace

CMD ["python", "-c", "print('DataPilot sandbox ready')"]
