import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.features.file_completion import rtf, service
RULES=json.loads((Path(__file__).resolve().parents[1]/'app/features/file_completion/data/rules.json').read_text(encoding='utf-8'))

def document(kind):
    title='Договор о предоставлении дополнительных социальных услуг' if kind=='additional' else 'Договор о предоставлении социальных услуг'
    if kind=='additional_act':title='Акт сдачи-приемки оказанных дополнительных услуг'
    amount='0,00' if kind=='free' else '120,00'
    text=title+'\nСтоимость Услуг, предусмотренных настоящим Договором, составляет '+amount+' рублей в месяц.\nКлиент Тестов, паспорт 1234, номер 42\n'
    for rule in RULES[kind]:text+=(rule['before']+'\n')*rule['count']
    return ('{\\rtf1\\ansi\\ansicpg1251\\uc1 '+rtf.escape(text)+'}').encode('ascii')

class CompletionTests(unittest.TestCase):
    def test_types_roundtrip_and_idempotency(self):
        for kind in service.TYPES:
            raw=document(kind)
            result,status,diff=service.transform(raw,kind,RULES)
            self.assertTrue(diff)
            self.assertIn('Клиент Тестов, паспорт 1234, номер 42',rtf.parse(result)[0])
            self.assertEqual(service.transform(result,kind,RULES)[0],result)
            self.assertEqual(service.transform(result,kind,RULES)[2],'')
            for other in service.TYPES:
                if other!=kind:
                    with self.assertRaises(ValueError):service.transform(raw,other,RULES)

    def test_partial_unknown_and_malformed(self):
        raw=document('free');text,_=rtf.parse(raw)
        rule=RULES['free'][0];m=service.locate(text,rule['before'])[0]
        partial=rtf.replace(raw,m.start(),m.end(),rule['after'])
        with self.assertRaises(ValueError):service.transform(partial,'free',RULES)
        for value in (b'not RTF',b'{\\rtf1 invalid',b'{\\rtf1\\bin5 abcde}'):
            with self.assertRaises(ValueError):rtf.parse(value)

    def test_edit_across_styles_preserves_groups_and_tables(self):
        raw=b"{\\rtf1\\ansi\\ansicpg1251 {\\fonttbl{\\f0 Arial;}}\\trowd\\cellx1000 {\\b Hello} world\\cell\\row}"
        text,_=rtf.parse(raw)
        self.assertNotIn('Arial',text)
        m=service.locate(text,'Hello world')[0]
        result=rtf.replace(raw,m.start(),m.end(),'Новый текст')
        self.assertIn('Новый текст',rtf.parse(result)[0])
        self.assertIn(b'\\trowd\\cellx1000',result)
        self.assertIn(b'\\cell\\row',result)

    def test_zip_queue_and_safe_output(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);archive=p/'input.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('../contract.rtf',document('paid'))
                z.writestr('unknown.txt','other')
            rows=service.read_inputs([archive])
            self.assertEqual(len(rows),2);self.assertIn('error',rows[1])
            result,status,diff=service.transform(rows[0]['raw'],'paid',RULES)
            rows[0].update(result=result,changed=True)
            target=p/'output.zip'
            self.assertEqual(service.save_results(rows,target,True),1)
            with zipfile.ZipFile(target) as z:
                self.assertTrue(all('/' not in n and '..' not in n for n in z.namelist()))
            with self.assertRaises(ValueError):service.save_results(rows,target,True)

    def test_multiline_payment_keeps_original_list_number(self):
        before = 'Оплата ____\nИнструкция ____'
        raw = ('{\\rtf1\\ansi\\uc1 {\\listtext 11.\\tab}\\pard\\ls1\\ilvl0\\fi567 '
               + rtf.escape('Оплата ____') + '\\par \\pard\\li0 '
               + rtf.escape('Инструкция ____') + '\\par }').encode('ascii')
        text, _ = rtf.parse(raw)
        match = service.locate(text,before)[0]
        result = rtf.replace(raw,match.start(),match.end(),'Услуги бесплатно.')
        self.assertIn('11.',rtf.parse(result)[0])
        self.assertEqual(result.count(b'\\pard'),1)
        self.assertIn(b'\\ls1\\ilvl0\\fi567',result)
        self.assertNotIn('Инструкция',rtf.parse(result)[0])

    def test_new_type_merges_with_existing_custom_rules(self):
        from unittest.mock import patch
        from app.features.file_completion import storage
        with tempfile.TemporaryDirectory() as directory, patch('app.core.storage.app_base_dir',return_value=directory):
            folder=Path(directory)/'data/file_completion';folder.mkdir(parents=True)
            previous={k:v for k,v in RULES.items() if k!='additional_act'}
            previous['free']=[dict(r) for r in previous['free']]
            previous['free'][0]['after']='Заказчик получает услуги без оплаты.'
            (folder/'rules.json').write_text(json.dumps(previous),encoding='utf-8')
            loaded=storage.load_rules()
            self.assertIn('additional_act',loaded)
            self.assertEqual(loaded['free'][0]['after'],'Заказчик получает услуги без оплаты.')
            service.validate_rules(loaded)
