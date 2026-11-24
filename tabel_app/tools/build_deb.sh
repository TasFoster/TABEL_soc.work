#!/usr/bin/env bash
# Собрать два пакета Ubuntu amd64 из того же VERSION, что и Windows.
set -euo pipefail

if [[ $# != 1 ]]; then
    echo "Использование: $0 <папка для пакетов>" >&2
    exit 2
fi
if [[ $(uname -s) != Linux || $(dpkg --print-architecture) != amd64 ]]; then
    echo 'Требуется среда Linux amd64' >&2
    exit 1
fi

out=$(realpath -m "$1")
mkdir -p "$out"
cd "$(dirname "$0")/.."
src=$PWD
version=$(<VERSION)
[[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'Некорректный VERSION' >&2; exit 1; }

build=$(mktemp -d)
trap 'rm -rf -- "$build"' EXIT
# Пакет содержит только ресурсы из этого списка и зависимости PyInstaller.
# Список должен соответствовать build.ps1. Рабочие базы пользователей не включаются.
resources=(
    timesheet/templates/f0504421_template.xls
    timesheet/data/departments.json
    timesheet/data/settings.json
    timesheet/data/calendar.json
    reestr/templates/reestr_template.ods
    reestr/data/settings.json
    reestr/data/grouping_seed.json
    prilozhenie/data/loads_seed.json
    uslugi_dengi/templates/uslugi_dengi_template.xlsx
    gos_zadanie/data/services_seed.json
    plany/data/plany_templates.json
    protokol/data/plan.json
    protokol/data/methodical_plans.json
    file_completion/data/rules.json
)
# VERSION читается и из дерева ресурсов frozen-приложения.
common=(
    --noconfirm --onedir --add-data "$src/VERSION:."
    --hidden-import xlrd --hidden-import sqlite3
    --collect-submodules xlwt --collect-submodules odf --collect-submodules openpyxl
    --collect-data customtkinter --collect-submodules customtkinter --hidden-import darkdetect
    --exclude-module winrt
)
for resource in "${resources[@]}"; do
    common+=(--add-data "$src/app/features/$resource:features/${resource%/*}")
done

for variant in full lite; do
    package=tabel
    title='Табель (полная версия)'
    dependencies='libc6 (>= 2.35), libx11-6, libxext6, libxft2, libxrender1, libfontconfig1, libfreetype6, libglib2.0-0, libstdc++6, xdg-utils, ca-certificates'
    if [[ $variant == full ]]; then
        dependencies+=', tesseract-ocr, tesseract-ocr-rus, tesseract-ocr-eng'
        args=(
            --collect-submodules app
            --add-data "$src/app/features/proezd/templates/proezd_template.ods:features/proezd/templates"
            --add-data "$src/app/features/proezd/data/settings.json:features/proezd/data"
        )
    else
        package=tabel-lite
        title='Табель (лёгкая версия)'
        args=(--exclude-module app.features.proezd --exclude-module cv2 --exclude-module numpy)
    fi
    python -m PyInstaller "${common[@]}" "${args[@]}" --name "$package" \
        --distpath "$build/dist" --workpath "$build/work" --specpath "$build" "$src/main.py"

    stage="$build/$package"
    install -d "$stage/DEBIAN" "$stage/usr/lib" "$stage/usr/bin" "$stage/usr/share/applications"
    mv "$build/dist/$package" "$stage/usr/lib/$package"
    cat > "$stage/DEBIAN/control" <<CONTROL
Package: $package
Version: $version
Architecture: amd64
Section: office
Priority: optional
Maintainer: Tabel project <farcrystas@gmail.com>
Installed-Size: $(du -sk "$stage/usr" | cut -f1)
Depends: $dependencies
Recommends: libreoffice-writer, libreoffice-calc
Homepage: https://github.com/TasFoster/TABEL_soc.work
Description: Desktop tools for social services departments ($variant)
 Generates timesheets and other office documents from department reports.
CONTROL
    ln -s "/usr/lib/$package/$package" "$stage/usr/bin/$package"
    cat > "$stage/usr/share/applications/$package.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=$title
Exec=$package
TryExec=$package
Terminal=false
Categories=Office;
Icon=x-office-spreadsheet
DESKTOP
    dpkg-deb --root-owner-group --build "$stage" "$out/${package}_${version}_amd64.deb"
done
