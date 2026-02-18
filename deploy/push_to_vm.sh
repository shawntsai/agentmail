#!/bin/bash
#
# Push AgentMail to your Oracle VM and run setup
#
# Usage:  bash deploy/push_to_vm.sh <your-vm-ip>
#
# Example: bash deploy/push_to_vm.sh 129.213.45.67
#

if [ -z "$1" ]; then
    echo "Usage: bash deploy/push_to_vm.sh <vm-ip>"
    echo "Example: bash deploy/push_to_vm.sh 129.213.45.67"
    exit 1
fi

VM_IP="$1"
VM_USER="${2:-ubuntu}"
SSH_KEY="/Users/shawn/workspace/agentmail/.ssh/ssh-key-2026-02-18.key"

echo ""
echo "Deploying AgentMail Relay to ${VM_USER}@${VM_IP}..."
echo ""

# Copy project files (exclude venv, data, git, ssh keys)
rsync -avz --progress \
    -e "ssh -i ${SSH_KEY}" \
    --exclude '.venv' \
    --exclude '__pycache__' \
    --exclude 'agentmail_data_*' \
    --exclude 'relay_data' \
    --exclude '.git' \
    --exclude '.ssh' \
    /Users/shawn/workspace/agentmail/ \
    "${VM_USER}@${VM_IP}:~/agentmail/"

echo ""
echo "Files copied. Now running setup on VM..."
echo ""

# Run setup script on VM
ssh -i "${SSH_KEY}" "${VM_USER}@${VM_IP}" "cd ~/agentmail && bash deploy/setup_oracle.sh"
