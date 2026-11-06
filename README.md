# site-qa
Проверка на всеки наш сайт на истински Windows (Chrome, Edge), Android и iPhone. Скилът е `cross-device-qa` в ai-os.
Детекторът е `checks/checks.js`: мери мастилото на буквите, изрязване, застъпване, хоризонтален скрол, шрифтове, грешки.

Пълен кръг: `./qa.sh <папка на сайта>` (пакет в частен release, Windows Chrome и Edge, iPhone, Android).
Само колелото на Windows: `gh workflow run detent.yml -f bundle=<таг>`.
Локално: `tests/detent_test.py` (колело), `tests/touch_test.py` (пръст през DevTools).
