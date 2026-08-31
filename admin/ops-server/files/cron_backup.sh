#!/bin/bash
# nightly backup job
rsync -a /data/ /backups/$(date +%F)/
