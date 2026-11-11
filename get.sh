#!/bin/bash
# Сваля и разшифрова резултатите: get.sh <id на кръг> [<id> ...]  → out/<id>/<платформа>/report.json + снимки
# Номерата ги печата qa.sh (или: gh run list -R inikolov-so/site-qa).
set -e
R=inikolov-so/site-qa; KEY="${SITE_QA_KEY:-$HOME/.config/site-qa/key}"
for r in "$@"; do
  OUT="out/$r"; mkdir -p "$OUT"
  gh run download "$r" -R $R -D "$OUT"
  find "$OUT" -name 'out.tgz.enc' | while read -r f; do
    d=$(dirname "$f")
    openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 -md sha256 -pass file:"$KEY" -in "$f" | tar xzf - -C "$d" --strip-components=1 && rm "$f"
  done
  echo "$OUT"; find "$OUT" -name report.json
done
