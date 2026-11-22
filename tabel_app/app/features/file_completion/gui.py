"""Очередь дополнения договоров и контроль правил пользователем."""
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from ...core import feedback
from . import FEATURE_TITLE, service, storage

HELP = '''1. Выберите вид договора или «Акты на государственные и дополнительные услуги» в списке сверху.
2. Добавьте один/несколько RTF или ZIP с документами. В одном запуске обрабатывается выбранный вид документа. Для актов меняется только подписант: директор → директор филиала; ФИО и должность доступны в правилах.
3. Нажмите «Проверить и подготовить». Выделите файл и откройте «Различия»: минус — удаление, плюс — добавление. Предпросмотр не записывает результат.
4. Сохраните подготовленные результаты в отдельную папку или новый ZIP. Исходники не меняются. Уже готовые договоры пропускаются; ошибки одного файла не мешают остальным.
Неверный тип, частично дополненный или незнакомый документ требует ручной проверки. Не переименовывайте DOC/DOCX в RTF — сначала сохраните его как RTF в офисной программе.
«Правила» показывают точные замены для всех типов. В after можно изменить добавляемые условия, ФИО директора и доверенность. before — ожидаемый исходный текст, count — число совпадений. Сохраняется предыдущая версия правил. После изменения правил или типа результаты нужно подготовить заново.
Результаты сохраняют таблицы и оформление исходного RTF. Перед использованием проверьте текст и печатный вид договора в Word/LibreOffice.'''


class CompletionWindow(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title('Дополнение файлов')
        self.geometry('980x650')
        self.rows = []
        self.kind = tk.StringVar(value=next(iter(service.TYPES.values())))
        top = ttk.Frame(self, padding=8); top.pack(fill='x')
        ttk.Button(top,text='Помощь',command=lambda:self.show_text('Помощь',HELP)).pack(side='right')
        feedback.add_button(top, self, FEATURE_TITLE, side="right", padx=6)
        combo=ttk.Combobox(top,textvariable=self.kind,values=list(service.TYPES.values()),state='readonly',width=58)
        combo.pack(side='left');combo.bind('<<ComboboxSelected>>',lambda e:self.invalidate())
        from .act_gui import open_editor
        ttk.Button(self, text="Редактор актов Word…", command=lambda: open_editor(self)).pack(anchor="w", padx=10)
        actions=ttk.Frame(self,padding=8);actions.pack(fill='x')
        for title,command in [('Добавить RTF / ZIP',self.add),('Удалить выбранные',self.remove),('Правила',self.rules),('Проверить и подготовить',self.prepare),('Различия',self.diff)]:
            ttk.Button(actions,text=title,command=command).pack(side='left',padx=3)
        self.table=ttk.Treeview(self,columns=('file','status'),show='headings',selectmode='extended')
        self.table.heading('file',text='Файл');self.table.heading('status',text='Результат проверки')
        self.table.column('file',width=420);self.table.column('status',width=480)
        scroll=ttk.Scrollbar(self,command=self.table.yview);scroll.pack(side='right',fill='y')
        self.table.configure(yscrollcommand=scroll.set);self.table.pack(fill='both',expand=True,padx=8)
        self.table.bind('<Double-1>',lambda e:self.diff())
        bottom=ttk.Frame(self,padding=8);bottom.pack(fill='x')
        ttk.Button(bottom,text='Сохранить в папку',command=lambda:self.save(False)).pack(side='right')
        ttk.Button(bottom,text='Сохранить ZIP',command=lambda:self.save(True)).pack(side='right',padx=6)
        self.status=tk.StringVar(value='Добавьте договоры для проверки.')
        ttk.Label(bottom,textvariable=self.status).pack(side='left')
        self.protocol('WM_DELETE_WINDOW',self.close)

    def close(self):
        if any(r.get('changed') for r in self.rows) and not messagebox.askyesno('Выход','Закрыть окно? Несохранённые результаты будут потеряны.',parent=self):return
        self.destroy()

    def refresh(self):
        self.table.delete(*self.table.get_children())
        for i,row in enumerate(self.rows):self.table.insert('', 'end',iid=str(i),values=(row['name'],row.get('error') or row.get('status','Ожидает проверки')))

    def invalidate(self):
        for row in self.rows:
            for key in ('result','changed','diff','status'):row.pop(key,None)
        self.refresh()

    def add(self):
        paths=filedialog.askopenfilenames(parent=self,filetypes=[('Договоры и архивы','*.rtf *.zip')])
        if paths:
            self.rows.extend(service.read_inputs(paths));self.refresh()

    def remove(self):
        for i in sorted(map(int,self.table.selection()),reverse=True):del self.rows[i]
        self.refresh()

    def prepare(self):
        try:rules=storage.load_rules();service.validate_rules(rules)
        except Exception as exc:messagebox.showerror('Правила',str(exc),parent=self);return
        self.invalidate()
        kind=next(k for k,v in service.TYPES.items() if v==self.kind.get())
        for row in self.rows:
            if 'raw' not in row:continue
            try:
                result,status,diff=service.transform(row['raw'],kind,rules)
                row.update(result=result,status=status,diff=diff,changed=bool(diff))
            except Exception as exc:row['status']=str(exc)
        self.refresh()
        ready=sum(bool(r.get('changed')) for r in self.rows)
        skipped=sum(r.get('status')=='Уже готов — пропущен' for r in self.rows)
        self.status.set(f'Подготовлено: {ready}. Уже готово: {skipped}. Остальные: {len(self.rows)-ready-skipped}.')

    def show_text(self,title,value):
        win=tk.Toplevel(self);win.title(title);win.geometry('900x650')
        text=ScrolledText(win,wrap='word',font=('Segoe UI',11));text.pack(fill='both',expand=True)
        text.tag_configure('added',foreground='#17652b');text.tag_configure('removed',foreground='#9c2020')
        for line in value.splitlines(True):text.insert('end',line,'added' if line.startswith('+') else 'removed' if line.startswith('-') else '')
        text.configure(state='disabled')

    def diff(self):
        selected=self.table.selection()
        if selected:
            row=self.rows[int(selected[0])]
            self.show_text('Текстовые различия — '+row['name'],row.get('diff') or row.get('status') or row.get('error') or 'Сначала подготовьте результат.')

    def rules(self):
        try:value=storage.load_rules()
        except Exception as exc:messagebox.showerror('Правила',str(exc),parent=self);return
        win=tk.Toplevel(self);win.title('Правила — before / after / count');win.geometry('950x700')
        text=ScrolledText(win,wrap='word');text.pack(fill='both',expand=True)
        text.insert('1.0',json.dumps(value,ensure_ascii=False,indent=2))
        def save():
            try:storage.save_rules(json.loads(text.get('1.0','end')))
            except Exception as exc:messagebox.showerror('Правила',str(exc),parent=win);return
            self.invalidate();win.destroy()
        ttk.Button(win,text='Сохранить новую версию правил',command=save).pack(pady=8)

    def save(self,zipped):
        target=filedialog.asksaveasfilename(parent=self,defaultextension='.zip',filetypes=[('ZIP','*.zip')]) if zipped else filedialog.askdirectory(parent=self)
        if not target:return
        try:count=service.save_results(self.rows,target,zipped)
        except Exception as exc:messagebox.showerror('Сохранение',str(exc),parent=self);return
        self.status.set(f'Сохранено файлов: {count}.')
        for row in self.rows:row['changed']=False


def open_file_completion(master):return CompletionWindow(master)
