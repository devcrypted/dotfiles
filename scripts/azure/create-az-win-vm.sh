#!/usr/bin/env bash
# Create a Windows 11 VM in Azure with a random admin password. Needs `az login` first.
set -eu # no pipefail: `tr | head` ends with SIGPIPE by design

location='centralindia'
rg='Win11-VM-RG'
name='Win11-VM'
dnsname='win11-demo-vm01'
adminuser='Devcrypted'
adminpassword=$(
  tr -dc 'A-Za-z0-9#@^&*!' </dev/urandom | head -c 18
  echo
)

az group create --name "$rg" --location "$location" >/dev/null

az vm create --name "$name" \
  --resource-group "$rg" \
  --admin-username "$adminuser" \
  --admin-password "$adminpassword" \
  --authentication-type 'password' \
  --computer-name 'Win11' \
  --license-type 'Windows_Client' \
  --location "$location" \
  --nsg-rule 'RDP' \
  --os-disk-caching 'ReadWrite' \
  --os-disk-delete-option 'Delete' \
  --os-disk-name "$name-osdisk" \
  --os-disk-size-gb '127' \
  --image 'MicrosoftWindowsDesktop:windows-11:win11-23h2-ent:22631.4602.241205' \
  --public-ip-address-dns-name "$dnsname" \
  --size 'Standard_D2ads_v5' \
  --ultra-ssd-enabled true \
  --output table

echo "Please Run 'mstsc /v:$dnsname.$location.cloudapp.azure.com /f'"
echo "Username: $adminuser"
echo "Password: $adminpassword"

## Delete the VM
# az vm delete --name "$name" --resource-group "$rg"
## Delete RG
# az group delete --name "$rg"
