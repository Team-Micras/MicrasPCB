#!/usr/bin/env bash
# KiCad 10 from the official PPA, with the source and its signing key written explicitly
# (add-apt-repository silently added nothing on the ubuntu-26.04 runner, so apt fell back to the
# distribution's KiCad 9). Fails unless kicad-cli reports the KICAD_VERSION in versions.env.
set -euo pipefail
cd "$(dirname "$0")/.."
. ./versions.env
. /etc/os-release

PPA=https://ppa.launchpadcontent.net/kicad/kicad-10.0-releases/ubuntu/
KEY=FDA854F61C4D0D9572BB95E5245D5502FAD7A805 # api.launchpad.net/1.0/~kicad/+archive/ubuntu/kicad-10.0-releases

sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x$KEY" | sudo gpg --batch --yes --dearmor -o /etc/apt/keyrings/kicad.gpg
printf 'Types: deb\nURIs: %s\nSuites: %s\nComponents: main\nSigned-By: /etc/apt/keyrings/kicad.gpg\n' \
  "$PPA" "$VERSION_CODENAME" | sudo tee /etc/apt/sources.list.d/kicad-10.0-releases.sources >/dev/null
sudo apt-get update -q
apt-cache policy kicad
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends kicad

got="$(kicad-cli version)"
if [ "$got" != "$KICAD_VERSION" ]; then
  echo "::error::KiCad $got installed, versions.env pins $KICAD_VERSION. Bump KICAD_VERSION (and regenerate) in its own PR."
  exit 1
fi
