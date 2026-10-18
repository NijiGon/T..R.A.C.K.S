"""Sends a car's outbox to central. Safe to retry: events keep their UUIDs, and central ignores repeats."""

import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger("krl.sync")


def post_events(url, token, car_id, events, timeout=10):
    """POST one batch. Returns True only when central answers with a 2xx."""
    body = json.dumps({
        "car_id": car_id,
        "events": [
            {
                "event_id": e.event_id,
                "door": e.door,
                "occurred_at": e.occurred_at,
                "direction": e.direction,
                "seat_delta": e.seat_delta,
            }
            for e in events
        ],
    }).encode()
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except urllib.error.HTTPError as error:
        log.warning("Central refused %d events with HTTP %s", len(events), error.code)
    except OSError as error:
        log.warning("Could not send %d events: %s", len(events), error)
    return False


def sync_once(outbox, send, batch_size=200):
    """Send pending events in batches. Returns (events sent, whether every batch went through).

    Events are marked sent only after a batch is acknowledged. On the first failure, the rest stay pending.
    """
    sent = 0
    while True:
        events = outbox.pending(batch_size)
        if not events:
            return sent, True
        if not send(events):
            return sent, False
        outbox.mark_sent([e.event_id for e in events])
        sent += len(events)


def sync_forever(outbox, send, stop, interval_s=5.0, max_backoff_s=60.0):
    """Keep syncing until `stop` is set. Waits longer after each failure, up to `max_backoff_s`."""
    delay = interval_s
    while not stop.is_set():
        _sent, ok = sync_once(outbox, send)
        delay = interval_s if ok else min(delay * 2, max_backoff_s)
        stop.wait(delay)
