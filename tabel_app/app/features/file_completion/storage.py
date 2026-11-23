import json
from pathlib import Path
from ...core import storage
PACKAGE = str(Path(__file__).parent)

def load_rules():
    default_path = Path(storage.feature_resource_dir('file_completion', PACKAGE)) / 'data/rules.json'
    defaults = json.loads(default_path.read_text(encoding='utf-8'))
    path = Path(storage.feature_data_dir('file_completion')) / 'rules.json'
    if path.exists():
        # Новые типы доступны после обновления, прежние пользовательские правки сохраняются.
        custom = json.loads(path.read_text(encoding='utf-8'))
        for kind in ('additional_act', 'additional'):
            for rule in custom.get(kind, []):
                standard = defaults[kind][0]
                if rule.get('before') == standard['before']:
                    variants = rule.setdefault('before_variants', [])
                    for variant in standard.get('before_variants', []):
                        if variant not in variants:
                            variants.append(variant)
        defaults.update(custom)
    return defaults


def save_rules(rules):
    from .service import validate_rules
    validate_rules(rules)
    old = load_rules()
    from datetime import datetime
    storage.save_json('file_completion', 'rules_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json', old)
    storage.save_json('file_completion', 'rules.json', rules)
