# src/messaging/stream.py
import os
import json
import asyncio
import redis.asyncio as redis

STREAM_NAME = os.getenv("INVENTORY_STREAM", "inventory_stream")
GROUP_NAME = "processor"  # consumer group

def get_redis():
    url = os.getenv("REDIS_URL")
    if not url:
        raise RuntimeError("REDIS_URL not set")
    return redis.from_url(url, decode_responses=True)

async def ensure_group(r: redis.Redis):
    # Crea consumer group se non esiste (MKSTREAM=True per creare stream vuota)
    try:
        await r.xgroup_create(name=STREAM_NAME, groupname=GROUP_NAME, id="$", mkstream=True)
    except redis.ResponseError as e:
        # Già esiste
        if "BUSYGROUP" not in str(e):
            raise

async def publish_inventory(chat_id: int, title: str, file_format: str, telegram_file_id: str):
    r = get_redis()
    try:
        payload = {
            "chat_id": chat_id,
            "title": title,
            "format": file_format,
            "telegram_file_id": telegram_file_id,
        }
        # Inseriamo come singolo campo "payload" JSON per semplicità
        msg_id = await r.xadd(STREAM_NAME, {"payload": json.dumps(payload)})
        return msg_id
    finally:
        await r.aclose()

async def consume_forever(process_fn, consumer_name: str):
    r = get_redis()
    await ensure_group(r)
    try:
        while True:
            # BLOCK 10s, 1 alla volta per semplicità
            records = await r.xreadgroup(
                groupname=GROUP_NAME,
                consumername=consumer_name,
                streams={STREAM_NAME: ">"},
                count=1,
                block=10_000,
            )
            if not records:
                continue

            for stream, messages in records:
                for msg_id, fields in messages:
                    try:
                        payload = json.loads(fields["payload"])
                        await process_fn(payload)  # elaborazione custom
                        await r.xack(STREAM_NAME, GROUP_NAME, msg_id)
                    except Exception as e:
                        # Non facciamo XACK: il messaggio resta in PEL per retry o ispezione
                        # (si possono aggiungere dead-letter logic e requeue in futuro)
                        print(f"[processor] errore su {msg_id}: {e}")
    finally:
        await r.aclose()
