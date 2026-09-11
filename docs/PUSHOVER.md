# Owner phone notifications

The owner selected Pushover. `pushover.py` is the central provider client.
`notify.py` is its reusable command interface.
The setup message reached the owner's phone on September 11, 2026, with explicit confirmation.

Store `PUSHOVER_APP_TOKEN` and `PUSHOVER_USER_KEY` in `.env`.
Environment variables take precedence. Do not print or commit credentials.
Status reports configuration fields without their values.

```sh
python3 notify.py status
python3 notify.py send --incident UNIQUE_ID --message 'Actionable owner message'
python3 notify.py confirm --incident UNIQUE_ID --evidence CONFIRMATION_PATH
```

Status and confirmation use local files only. Send makes an HTTPS request through the central client.
Confirm requires saved evidence that the owner received that specific message.
Pushover's successful API response means queued. It does not prove delivery to the phone.

The client saves incident identities, content fingerprints, attempt records and sanitized request identifiers.
It does not save credentials or raw provider errors.
Repeated incident identities suppress another request, including after a process restart.
The client rejects an incident identity reused with different content or another recipient.

The local limit is 50 attempts per rolling day, with at least five seconds between sends.
The client serializes sends and permits at most two attempts per incident.
It retries once after an explicit server rejection, with a five-second delay.
It does not retry client rejection or an ambiguous transport outcome.
These are local limits, not a statement of the provider's remaining allowance.

An interrupted send can retain `sending` status. Treat that status as uncertain.
Inspect the phone and saved evidence before any recovery decision.
Do not change the incident identity to evade duplicate protection.

Browser failure and phone notification use separate paths.
Failure to inspect Sleeper must not prevent an attempt to notify the owner.
Notification failures remain visible beside the workflow result.
An offline Mac requires a separate external monitor, which is not configured.

Reference: [Pushover Message API](https://pushover.net/api).
