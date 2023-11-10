ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG C.UTF-8

# Copy data for add-on
COPY eq_alert.py /

RUN echo "http://208.74.142.61/alpine/v3.12/main" >> /etc/apk/repositories      && \ 
    echo "http://208.74.142.61/alpine/v3.12/community" >> /etc/apk/repositories

# Install requirements for add-on
RUN apk add --no-cache python3 py3-pip

RUN pip3 install requests telethon asyncio-paho

# Python 3 HTTP Server serves the current working dir
# So let's set it to our add-on persistent data directory.
# WORKDIR /data

# RUN chmod a+x /run.sh

CMD [ "python3", "eq_alert.py" ]