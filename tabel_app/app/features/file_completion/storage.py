import json
from pathlib import Path
from ...core import storage
PACKAGE = str(Path(__file__).parent)

def load_rules():
    path = Path(storage.feature_data_dir('file_completion')) / 'rules.json'
    if not path.exists():
        path = Path(storage.feature_resource_dir('file_completion', PACKAGE)) / 'data/rules.json'
    return json.loads(path.read_text(encoding='utf-8'))

def save_rules(rules):
    from .service import validate_rules
    validate_rules(rules)
    old = load_rules()
    from datetime import datetime
    storage.save_json('file_completion', 'rules_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json', old)
    storage.save_json('file_completion', 'rules.json', rules)
