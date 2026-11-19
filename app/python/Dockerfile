# Flask test app run under Beacon Python. Dependencies install only if every wheel matches its pinned hash.
FROM python:3.12.7-slim@sha256:60d9996b6a8a3689d36db740b49f4327be3be09a21122bd02fb8895abb38b50d
WORKDIR /work
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r /tmp/requirements.txt \
 && pip check \
 && mkdir /evidence
COPY vulnapp/ /work/vulnapp/
COPY run.py /work/run.py
ENV BEACON_SECURITY_PYTHON_INCLUDE=vulnapp
EXPOSE 8080
CMD ["beacon", "python", "run.py"]
