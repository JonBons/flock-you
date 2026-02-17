#!/bin/bash
# Run the Flock You Ansible playbook against the Pi.
# Usage: ./run.sh [optional limit host]  e.g. ./run.sh flock_pi
set -e
cd "$(dirname "$0")"
LIMIT="${1:+-l $1}"
ansible-playbook -i inventory.yml playbook.yml $LIMIT
