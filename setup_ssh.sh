#!/bin/bash
rm -f /c/Users/Lenovo/.ssh/id_ed25519 /c/Users/Lenovo/.ssh/id_ed25519.pub
ssh-keygen -t ed25519 -C water2878 -f /c/Users/Lenovo/.ssh/id_ed25519 -N ''
echo "=== PUBLIC KEY ==="
cat /c/Users/Lenovo/.ssh/id_ed25519.pub
echo "=== TESTING SSH ==="
ssh -T git@github.com 2>&1 || true
