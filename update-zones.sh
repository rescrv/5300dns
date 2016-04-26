#!/bin/zsh
set -e
/usr/sbin/python /home/rescrv/dns.py zone > /tmp/zone.tmp
mv /tmp/zone.tmp /etc/nsd/bigdata.systems.zone
pkill -HUP nsd
