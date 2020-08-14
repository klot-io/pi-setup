FROM klotio/flask:0.2

COPY requirements.txt .

RUN apk add --no-cache --virtual .pip-deps git && \
    pip install --no-cache-dir -r requirements.txt && \
    apk del --no-network .pip-deps \
	&& find /usr/local -depth \
		\( \
			\( -type d -a \( -name test -o -name tests -o -name idle_test \) \) \
			-o \
			\( -type f -a \( -name '*.pyc' -o -name '*.pyo' \) \) \
		\) -exec rm -rf '{}' +

COPY bin bin
COPY lib lib

CMD "/opt/service/bin/api.py"
