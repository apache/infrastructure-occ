FROM alpine:latest

LABEL project="https://github.com/apache/infrastructure-occ"

ARG WDIR=/usr/src/occ
ARG CDIR=/etc/occ
ARG GIT_OCCVER=main

RUN apk --no-cache add python3 py-pip git

RUN git clone -b $GIT_OCCVER https://github.com/nser77/infrastructure-occ.git $WDIR

WORKDIR $WDIR

RUN pip install -r requirements.txt

RUN apk --no-cache del git py-pip

RUN mkdir $CDIR

ENTRYPOINT ["/usr/bin/python", "-u", "occ.py", "--config-file", "/etc/occ/occ.yaml"]
