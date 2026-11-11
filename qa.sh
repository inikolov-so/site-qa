#!/bin/bash
# Проверка на всички платформи преди публикуване: qa.sh <папка на готовия сайт> [страници]
# Пакетира папката, шифрова я (репото е публично) и пуска Windows (Chrome, Edge), iPhone и Android.
# Ключът е в ~/.config/site-qa/key и в тайната QA_KEY на репото. Резултатите: ./get.sh <таг>
set -e
DIR="$1"; PAGES="${2:-}"; TAG="qa-$(date +%m%d-%H%M)"; R=inikolov-so/site-qa
KEY="${SITE_QA_KEY:-$HOME/.config/site-qa/key}"
[ -s "$KEY" ] || { echo "Няма ключ $KEY"; exit 1; }
T=$(mktemp -d)
tar czf "$T/site.tgz" --exclude=.vercel -C "$DIR" .
openssl enc -aes-256-cbc -pbkdf2 -iter 100000 -md sha256 -salt -pass file:"$KEY" -in "$T/site.tgz" -out "$T/site.tgz.enc"
gh release create "$TAG" "$T/site.tgz.enc" -R $R -n "шифрован пакет за проверка" -t "$TAG" --latest=false >/dev/null
rm -rf "$T"
gh workflow run desktop.yml -R $R -f bundle="$TAG" -f pages="$PAGES"
gh workflow run mobile.yml -R $R -f bundle="$TAG" -f pages="$PAGES"
sleep 6
echo "$TAG"; echo "Кръгове (за ./get.sh):"
gh run list -R $R -L 2 --json databaseId,workflowName -q '.[] | "\(.databaseId) \(.workflowName)"'
