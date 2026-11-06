#!/bin/bash
# Проверка на всички платформи преди публикуване: qa.sh <папка на готовия сайт> [страници]
# Пакетира папката, качва я в частното репо и пуска Windows (Chrome, Edge), iPhone и Android.
set -e
DIR="$1"; PAGES="${2:-}"; TAG="qa-$(date +%m%d-%H%M)"; R=inikolov-so/site-qa
tar czf /tmp/$TAG.tgz --exclude=.vercel -C "$DIR" . && mv /tmp/$TAG.tgz /tmp/site.tgz
gh release create "$TAG" /tmp/site.tgz -R $R -n "пакет за проверка" -t "$TAG" --latest=false >/dev/null
gh workflow run desktop.yml -R $R -f bundle="$TAG" -f pages="$PAGES"
gh workflow run mobile.yml -R $R -f bundle="$TAG" -f pages="$PAGES"
echo "$TAG"
