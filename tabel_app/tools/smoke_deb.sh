#!/usr/bin/env bash
# Проверка внутри одноразовой Ubuntu: установка, запуск, обновление, сохранение данных.
set -euo pipefail
out=$(realpath "${1:?Укажите каталог с пакетами}")
version=$(<"$(dirname "$0")/../VERSION")
check_dir=$(mktemp -d)
trap 'rm -rf -- "$check_dir"' EXIT
mkdir "$check_dir/home"
export HOME="$check_dir/home" XDG_DATA_HOME="$check_dir/xdg"

# Имитируем первое обновление Linux-пакета до появления предыдущего публичного
# выпуска: содержимое прежнее, но версия в метаданных пакета заведомо меньше.
for package in tabel tabel-lite; do
    target="$out/${package}_${version}_amd64.deb"
    stage="$check_dir/$package"
    dpkg-deb --raw-extract "$target" "$stage"
    sed -i 's/^Version: .*/Version: 0~smoke/' "$stage/DEBIAN/control"
    dpkg-deb -Zgzip -z1 --root-owner-group --build "$stage" "$check_dir/$package.deb"
done
sudo apt-get install -y --no-install-recommends "$check_dir/tabel.deb" "$check_dir/tabel-lite.deb"

check_install() {
    local package=$1 variant=$2 installed_version=$3
    [[ $(dpkg-query -W -f='${Version}' "$package") == "$installed_version" ]]
    desktop-file-validate "/usr/share/applications/$package.desktop"
    rm -f "$XDG_DATA_HOME/$package/selftest_release_result.json"
    xvfb-run -a timeout 120 "$package" --selftest-release --selftest-desktop "$variant" "$version"
    python3 - "$XDG_DATA_HOME/$package/selftest_release_result.json" <<'PY'
import json
import sys
from pathlib import Path
result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if not result["ok"]:
    raise SystemExit(result["error"])
print(result["version"], result["features"])
PY
}

check_install tabel full 0~smoke
check_install tabel-lite lite 0~smoke
python3 - <<'PY'
import os
import sqlite3
from pathlib import Path

for package in ("tabel", "tabel-lite"):
    base = Path(os.environ["XDG_DATA_HOME"]) / package / "data"
    with sqlite3.connect(base / "app.db") as connection:
        connection.execute("INSERT INTO meta (key, value) VALUES ('install_smoke', ?)", (package,))
    (base / "local-settings.json").write_text(package, encoding="utf-8")
PY
sudo apt-get install -y --no-install-recommends "$out/tabel_${version}_amd64.deb" "$out/tabel-lite_${version}_amd64.deb"
check_install tabel full "$version"
check_install tabel-lite lite "$version"
python3 - <<'PY'
import os
import sqlite3
from pathlib import Path

for package in ("tabel", "tabel-lite"):
    base = Path(os.environ["XDG_DATA_HOME"]) / package / "data"
    with sqlite3.connect(base / "app.db") as connection:
        assert connection.execute("SELECT value FROM meta WHERE key = 'install_smoke'").fetchone() == (package,)
    assert (base / "local-settings.json").read_text(encoding="utf-8") == package
PY
