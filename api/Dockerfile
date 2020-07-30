FROM klotio/flask:0.1

RUN mkdir -p /opt/service

WORKDIR /opt/service

COPY requirements.txt .

RUN apk add --no-cache --virtual .pip-deps git && \
    pip install --no-cache-dir -r requirements.txt && \
    apk del --no-network .pip-deps

COPY bin bin
COPY lib lib

ENV PYTHONPATH "/opt/service/lib:${PYTHONPATH}"

CMD "/opt/service/bin/api.py"
