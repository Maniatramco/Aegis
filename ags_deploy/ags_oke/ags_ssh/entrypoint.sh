#!/bin/sh
set -eu
# Kubernetes fsGroup may add group bits to Secret files. OpenSSH requires the
# host key to be private; copy it to a root-owned location with exact modes.
cp /run/ssh-keys/ssh_host_ed25519_key /run/ssh-host/ssh_host_ed25519_key
chmod 600 /run/ssh-host/ssh_host_ed25519_key
cp /run/ssh-keys/authorized_keys /run/ssh-host/authorized_keys
chmod 644 /run/ssh-host/authorized_keys
exec /usr/sbin/sshd -D -e -f /etc/ssh/sshd_config
