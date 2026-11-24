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
    if kind=='additional_agreement':
        title = ('Дополнительное соглашение № 12-З-09\n'
                 'к договору о предоставлении дополнительных социальных услуг')
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

    def test_additional_contract_blank_payment_template(self):
        rule = RULES['additional'][0]
        raw = document('additional')
        match, = service.locate(rtf.parse(raw)[0], rule['before'])
        draft = rtf.replace(raw, *match.span(), rule['before_variants'][0])
        result, _, diff = service.transform(draft, 'additional', RULES)
        self.assertTrue(diff)
        expected = rtf.parse(raw)[0]
        for standard in RULES['additional']:
            expected = expected.replace(standard['before'], standard['after'])
        self.assertEqual(rtf.parse(result)[0], expected)
        self.assertEqual(service.transform(result, 'additional', RULES)[2], '')

    def test_additional_contract_completes_payment_and_both_signatures_independently(self):
        payment, signature, authority = RULES['additional']
        original_text = ('Договор о предоставлении дополнительных социальных услуг\n'
                         'Заказчик Тестов Тест Тестович\n' + payment['before'] + '\n')
        original_text += ('Директор\n' + signature['before'] + '\n' +
                          authority['before'] + '\nМ.П.\tЗаказчик\n') * 2
        expected = original_text
        for rule in (payment, signature, authority):
            expected = expected.replace(rule['before'], rule['after'])

        for already_complete in ((), (payment,), (signature, authority)):
            with self.subTest(already_complete=len(already_complete)):
                draft = original_text
                for rule in already_complete:
                    draft = draft.replace(rule['before'], rule['after'])
                raw = ('{\\rtf1\\ansi\\uc1 ' + rtf.escape(draft) + '}').encode('ascii')
                result, _, diff = service.transform(raw, 'additional', RULES)
                self.assertTrue(diff)
                self.assertEqual(rtf.parse(result)[0], expected)
                self.assertEqual(service.transform(result, 'additional', RULES),
                                 (result, 'Уже готов — пропущен', ''))

        draft = original_text.replace(signature['before'], signature['after'], 1)
        raw = ('{\\rtf1\\ansi\\uc1 ' + rtf.escape(draft) + '}').encode('ascii')
        with self.assertRaisesRegex(ValueError, 'частично дополненный'):
            service.transform(raw, 'additional', RULES)

    def test_legacy_additional_payment_rules_gain_signature_fields(self):
        from unittest.mock import patch
        from app.features.file_completion import storage
        with tempfile.TemporaryDirectory() as directory, patch(
            'app.core.storage.app_base_dir', return_value=directory
        ):
            folder = Path(directory) / 'data/file_completion'
            folder.mkdir(parents=True)
            path = folder / 'rules.json'
            payment, signature, authority = RULES['additional']
            custom_payment = dict(payment, after='Согласованный порядок оплаты.')
            existing = {'additional': [custom_payment]}
            path.write_text(json.dumps(existing), encoding='utf-8')
            loaded = storage.load_rules()
            self.assertEqual(loaded['additional'], [custom_payment, signature, authority])
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), existing)

            custom_signature = dict(signature, before='Пустая подпись', after='Новая подпись')
            loaded['additional'][1] = custom_signature
            storage.save_rules(loaded)
            self.assertEqual(storage.load_rules()['additional'],
                             [custom_payment, custom_signature, authority])

    def test_additional_agreement_changes_only_signature_fields(self):
        kind = 'additional_agreement'
        signature, authority = RULES[kind]
        block = ('Директор\n' + signature['before'] + '\nподпись руководителя\n'
                 + authority['before'] + '\nМ.П.\tТестов Тест Тестович/___________\n')
        text = ('Дополнительное соглашение № 12-З-09\n'
                'к договору о предоставлении дополнительных социальных услуг\n'
                'Заказчик: Тестов Тест Тестович\n' + block * 2)
        raw = ('{\\rtf1\\ansi\\uc1 ' + rtf.escape(text) + '}').encode('ascii')
        result, _, diff = service.transform(raw, kind, RULES)
        expected = text.replace(signature['before'], signature['after']).replace(
            authority['before'], authority['after'])
        self.assertTrue(diff)
        self.assertEqual(rtf.parse(result)[0], expected)
        self.assertEqual(service.transform(result, kind, RULES)[2], '')

        match = service.locate(text, signature['before'])[0]
        partial = rtf.replace(raw, *match.span(), signature['after'])
        with self.assertRaises(ValueError):
            service.transform(partial, kind, RULES)

        with tempfile.TemporaryDirectory() as directory:
            rows = [{'name': 'draft.rtf', 'result': result, 'changed': True}]
            service.save_results(rows, directory)
            self.assertEqual([p.name for p in Path(directory).iterdir()],
                             ['Тестов_Тест_Тестович_допсоглашение.rtf'])

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
            previous={k:v for k,v in RULES.items() if k not in ('additional_act', 'additional_agreement')}
            previous['free']=[dict(r) for r in previous['free']]
            previous['free'][0]['after']='Заказчик получает услуги без оплаты.'
            (folder/'rules.json').write_text(json.dumps(previous),encoding='utf-8')
            loaded=storage.load_rules()
            self.assertIn('additional_act',loaded)
            self.assertIn('additional_agreement', loaded)
            self.assertEqual(loaded['free'][0]['after'],'Заказчик получает услуги без оплаты.')
            service.validate_rules(loaded)

    def test_unified_act_headings_keep_original_text(self):
        for heading in ('Акт сдачи-приемки оказанных дополнительных услуг',
                        'Акт сдачи-приемки оказанных социальных услуг',
                        'Акт сдачи-приемки оказанных государственных услуг',
                        'Акт сдачи-приёмки оказанных государственных социальных услуг'):
            text=heading+'\nЗаказчик Тестовый\n'+RULES['additional_act'][0]['before']
            raw=('{\\rtf1\\ansi\\uc1 '+rtf.escape(text)+'}').encode('ascii')
            result,status,diff=service.transform(raw,'additional_act',RULES)
            self.assertIn(heading,rtf.parse(result)[0])
            self.assertIn('Заказчик Тестовый',rtf.parse(result)[0])
            self.assertIn('Директор филиала',rtf.parse(result)[0])
            self.assertEqual(service.transform(result,'additional_act',RULES)[0],result)
            with self.assertRaises(ValueError):service.transform(raw,'free',RULES)

    def test_government_act_blank_signature_variant(self):
        text='Акт сдачи-приемки оказанных социальных услуг\nДиректор филиала _________________________ (_______________)\nПолучатель Тестовый'
        raw=('{\\rtf1\\ansi\\uc1 '+rtf.escape(text)+'}').encode('ascii')
        result,_,diff=service.transform(raw,'additional_act',RULES)
        self.assertIn('(Колесниченко Е.И.)',rtf.parse(result)[0])
        self.assertIn('Получатель Тестовый',rtf.parse(result)[0])
        self.assertEqual(service.transform(result,'additional_act',RULES)[2],'')
