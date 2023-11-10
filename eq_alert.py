import os
import re
import asyncio
import json
import logging
import sys
import traceback
import time
from functools import wraps

import requests
from asyncio_paho import AsyncioPahoClient
from telethon import TelegramClient, events
from telethon.sessions import StringSession

MIN_ALERT_INTERVAL_SECS = 120
MAX_WORD_DISTANCE = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] [%(levelname)s]  %(message)s",
    handlers=[
        logging.FileHandler("eq_alert.log"),
        logging.StreamHandler()
    ])
logger = logging.getLogger()

def exc_hander(exctype, value, tb):
    trace_str = traceback.format_exception(exctype, value, tb)
    logger.error("".join(trace_str))
sys.excepthook = exc_hander

def rate_limited(interval):
    def decorator(func):
        @wraps(func)
        async def wrapped(self, *args, **kwargs):
            if not hasattr(self, '_last_call'):
                self._last_call = {}

            if func.__name__ not in self._last_call:
                self._last_call[func.__name__] = 0

            elapsed_time = time.time() - self._last_call[func.__name__]
            if elapsed_time < interval:
                return
            self._last_call[func.__name__] = time.time()
            return await func(self, *args, **kwargs)
        return wrapped
    return decorator


class EarthquakeMonitor:
    def __init__(
        self,
        telegram_api_id,
        telegram_api_hash,
        telegram_session_hash,
        chat_names,
        mqtt_server,
        mqtt_port,
        mqtt_topic,
        mqtt_username=None,
        mqtt_password=None,
        debug=False
    ):
        self.telegram_api_id = telegram_api_id
        self.telegram_api_hash = telegram_api_hash
        self.telegram_session_hash = telegram_session_hash

        self.mqtt_server = mqtt_server
        self.mqtt_port = mqtt_port
        self.mqtt_topic = mqtt_topic
        self.mqtt_username = mqtt_username
        self.mqtt_password = mqtt_password
        
        self.chat_names = chat_names

        self.debug = debug
        if self.debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Debug mode enabled.")

        self.telegram_client = None
        self.mqtt_client = None
        self.alert_chat_ids = []

    async def main(self):
        logger.info("Configuring Telegram client...")

        self.telegram_client = TelegramClient(
            StringSession(self.telegram_session_hash),
            self.telegram_api_id,
            self.telegram_api_hash
        )
        logger.debug("Telegram client configured.")
        self.telegram_client.add_event_handler(
            self.message_handler,
            events.NewMessage(incoming=True)
        )
        logger.debug("Telegram event handler added.")
        await self.telegram_client.start()
        logger.debug("Telegram client started.")
        
        logger.info("Connecting to MQTT server...")
        self.mqtt_client = AsyncioPahoClient()
        self.mqtt_client.username_pw_set(
            self.mqtt_username,
            self.mqtt_password
        )
        await self.mqtt_client.asyncio_connect(
            self.mqtt_server,
            self.mqtt_port
        )
        logger.debug("MQTT client connected.")

        self.alert_chat_ids = []
        dialogs = await self.telegram_client.get_dialogs()
        for dialog in dialogs:
            if dialog.name in self.chat_names:
                logger.debug("Monitoring: %s (%d)", dialog.name, dialog.id)
                self.alert_chat_ids.append(dialog.id)

        logger.info("Listening for messages in chats: %s", ", ".join(
            [str(chat_id) for chat_id in self.alert_chat_ids]
        ))

        await self.telegram_client.run_until_disconnected()

    @rate_limited(120)
    async def message_handler(self, event):
        logger.info(f"Received message in {event.message.chat_id}: {event.message.raw_text}")
        if event.message.chat_id in self.alert_chat_ids:
            logger.info("Earthquake alert received.")
            raw_text = event.message.raw_text
            magnitude = self.find_magnitude(raw_text)
            if magnitude:
                mqtt_payload = json.dumps({
                    "magnitude": magnitude,
                    "complete_message": raw_text
                })
                logger.info(f"Publishing to MQTT: {mqtt_payload}")
                self.mqtt_client.publish(self.mqtt_topic, mqtt_payload)
                
    def find_magnitude(self, text):
        found_word = False
        word_distance = 0

        for word in text.split():
            if 'magnitudine' in word.lower():
                found_word = True
                continue

            if found_word:
                match = re.search(r"\d+[.,]\d+", word)
                if match:
                    print(word_distance)
                if match and word_distance < MAX_WORD_DISTANCE:
                    magnitude = match.group()
                    return magnitude
                
                word_distance += 1
        
        return None

    def __del__(self):
        self.telegram_client.disconnect()
        self.mqtt_client.disconnect()

if __name__ == '__main__':
    with open('/data/options.json', 'r') as fh:
        options = json.loads(fh.read())
        
        em = EarthquakeMonitor(
            options['telegram_api_id'],
            options['telegram_api_hash'],
            options['telegram_session_hash'],
            options['chat_names'],
            options['mqtt_server'],
            options['mqtt_port'],
            options.get('mqtt_topic', 'infp/eq_alert'),
            mqtt_username=options.get('mqtt_username'),
            mqtt_password=options.get('mqtt_password'),
            debug=options.get('debug', False)
        )


        loop = asyncio.get_event_loop()
        loop.run_until_complete(em.main())

    loop = asyncio.get_event_loop()
    loop.run_until_complete(em.main())
