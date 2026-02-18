# Deploy AgentMail Relay on Oracle Cloud (Free Forever)

## Step 1: Create Oracle Cloud Account

1. Go to https://cloud.oracle.com
2. Click "Sign Up" — create a free account
3. You need a credit card for verification but you will NOT be charged
4. The "Always Free" tier never expires

## Step 2: Create a Free VM

1. In the Oracle Cloud Console, go to **Compute > Instances**
2. Click **Create Instance**
3. Configure:
   - **Name**: `agentmail-relay`
   - **Image**: Ubuntu 22.04 (or latest)
   - **Shape**: VM.Standard.E2.1.Micro (this is the free one)
     - 1 OCPU, 1 GB RAM — more than enough
   - **Networking**: Use default VCN or create one
   - **SSH Key**: Upload your public key (`~/.ssh/id_rsa.pub`)
     - If you don't have one, run: `ssh-keygen -t rsa` on your laptop
4. Click **Create**
5. Wait ~2 minutes for it to boot

## Step 3: Open Port 7445 in Oracle Cloud Network

This is the step most people miss — Oracle has TWO firewalls.

### A. Security List (Oracle's cloud firewall)

1. Go to **Networking > Virtual Cloud Networks**
2. Click your VCN > Click your **Subnet** > Click the **Security List**
3. Click **Add Ingress Rule**:
   - Source CIDR: `0.0.0.0/0`
   - Destination Port Range: `7445`
   - Protocol: TCP
4. Save

### B. OS firewall (iptables — handled by the setup script)

The setup script handles this automatically.

## Step 4: SSH Into Your VM

Find the public IP in the Oracle Console (on the instance page).

```bash
ssh ubuntu@<your-vm-ip>
```

## Step 5: Deploy

Copy the agentmail code to the VM:

```bash
# From your laptop — copy the project to the VM
scp -r /Users/shawn/workspace/agentmail ubuntu@<your-vm-ip>:~/agentmail
```

Then on the VM:

```bash
# SSH into VM
ssh ubuntu@<your-vm-ip>

# Run the setup script
cd ~/agentmail
bash deploy/setup_oracle.sh
```

That's it. The script installs everything, starts the relay, and opens the port.

## Step 6: Use It

On your laptop:

```bash
cd /Users/shawn/workspace/agentmail
source .venv/bin/activate
python run.py --name alice --port 7443 --relay http://<your-vm-ip>:7445
```

Share `http://<your-vm-ip>:7445` with anyone you want to be able to message.

## Verify It's Working

```bash
# From your laptop
curl http://<your-vm-ip>:7445/v0/stats
# Should return: {"messages_held":0,"total_bytes":0}
```

## Useful Commands (on the VM)

```bash
# Check relay status
sudo systemctl status agentmail-relay

# View live logs
sudo journalctl -u agentmail-relay -f

# Restart relay
sudo systemctl restart agentmail-relay

# Stop relay
sudo systemctl stop agentmail-relay
```

## Cost

$0. Forever. The VM.Standard.E2.1.Micro shape is in Oracle's "Always Free" tier.
