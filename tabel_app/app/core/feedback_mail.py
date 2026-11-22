"""Создание письма с вложениями для почтовой программы пользователя."""
from email.message import EmailMessage
from email.policy import SMTP
import mimetypes
from pathlib import Path


def make_draft(recipient, subject, body, paths):
    message = EmailMessage(policy=SMTP)
    message["To"] = recipient
    message["Subject"] = subject
    message["X-Unsent"] = "1"
    message.set_content(body)
    for path in map(Path, paths):
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        main, subtype = mime.split("/", 1)
        message.add_attachment(path.read_bytes(), maintype=main, subtype=subtype, filename=path.name)
    return message.as_bytes()
