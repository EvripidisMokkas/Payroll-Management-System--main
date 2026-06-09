"""Django fields that transparently encrypt recoverable sensitive values."""

from django.db import models

from .crypto import decrypt, encrypt


class EncryptedTextField(models.TextField):
    description = "Application-level encrypted text"

    def from_db_value(self, value, expression, connection):
        return decrypt(value)

    def to_python(self, value):
        return decrypt(value)

    def get_prep_value(self, value):
        return super().get_prep_value(encrypt(value))
