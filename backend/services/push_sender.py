"""
Web Push delivery to the driver's subscribed devices (B5b).

Subscriptions live in blob storage (container `push-subscriptions`,
blob `driver.json` — a JSON list, deduped by endpoint). Sending uses
pywebpush with VAPID; the private key comes from the VAPID_PRIVATE_KEY
app setting and is never stored in code.

Everything here is best-effort by contract: callers hook this into the
booking path, so this module must never raise into a booking flow.
"""
import json
import logging
import os

CONTAINER = "push-subscriptions"
BLOB_NAME = "driver.json"
VAPID_CLAIM_SUB = "mailto:peter.teehan@costesla.com"


def _container_client():
    from azure.storage.blob import BlobServiceClient
    conn = os.environ["AzureWebJobsStorage"]
    svc = BlobServiceClient.from_connection_string(conn)
    container = svc.get_container_client(CONTAINER)
    try:
        container.create_container()
    except Exception:
        pass  # already exists
    return container


def get_subscriptions() -> list:
    try:
        blob = _container_client().get_blob_client(BLOB_NAME)
        data = json.loads(blob.download_blob().readall())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_subscriptions(subs: list) -> None:
    blob = _container_client().get_blob_client(BLOB_NAME)
    blob.upload_blob(json.dumps(subs), overwrite=True)


def add_subscription(subscription: dict) -> int:
    """Upsert by endpoint; returns the resulting count."""
    subs = [s for s in get_subscriptions() if s.get("endpoint") != subscription.get("endpoint")]
    subs.append(subscription)
    save_subscriptions(subs)
    return len(subs)


def remove_subscription(endpoint: str) -> int:
    subs = [s for s in get_subscriptions() if s.get("endpoint") != endpoint]
    save_subscriptions(subs)
    return len(subs)


def notify_driver(title: str, body: str, url: str = "/") -> dict:
    """Send a push to every subscribed driver device. Never raises."""
    try:
        subs = get_subscriptions()
        if not subs:
            return {"sent": 0, "reason": "no subscriptions"}

        private_key = os.environ.get("VAPID_PRIVATE_KEY")
        if not private_key:
            logging.warning("notify_driver: VAPID_PRIVATE_KEY not configured — skipping send")
            return {"sent": 0, "reason": "VAPID_PRIVATE_KEY not configured"}

        from pywebpush import webpush, WebPushException

        payload = json.dumps({"title": title, "body": body, "url": url, "tag": "costesla-driver"})
        sent = 0
        alive = []
        for sub in subs:
            try:
                # fresh claims dict per call — pywebpush mutates it (adds aud/exp)
                webpush(
                    subscription_info=sub,
                    data=payload,
                    vapid_private_key=private_key,
                    vapid_claims={"sub": VAPID_CLAIM_SUB},
                )
                sent += 1
                alive.append(sub)
            except WebPushException as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status in (404, 410):
                    logging.info("notify_driver: pruning dead subscription (endpoint gone)")
                else:
                    logging.warning(f"notify_driver: send failed ({status}): {e}")
                    alive.append(sub)
            except Exception as e:
                logging.warning(f"notify_driver: send failed: {e}")
                alive.append(sub)

        if len(alive) != len(subs):
            save_subscriptions(alive)
        return {"sent": sent, "total": len(subs)}
    except Exception as e:
        logging.error(f"notify_driver: unexpected failure: {e}")
        return {"sent": 0, "reason": str(e)}
