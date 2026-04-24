#!/bin/sh
# Fix volume permissions at runtime — Docker volumes mount as root, overriding
# the chown done in the Dockerfile image layer.
mkdir -p /data/chroma_db
touch /data/audit_trail.jsonl
chown -R appuser:appuser /data
exec gosu appuser python run_proxy.py
