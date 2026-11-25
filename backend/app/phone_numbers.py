"""Normalize Ghanaian and international telephone identifiers."""
import re
from typing import Annotated

from pydantic import AfterValidator, Field


def normalize_phone_number(identifier: str) -> str | None:
    number = re.sub(r'[\s().-]', '', identifier)
    if re.fullmatch(r'0[0-9]{9}', number):
        number = '+233' + number[1:]
    elif re.fullmatch(r'233[0-9]{9}', number):
        number = '+' + number
    return number if re.fullmatch(r'\+[1-9][0-9]{7,14}', number) else None


def require_phone_number(value: str) -> str:
    number = normalize_phone_number(value)
    if number is None:
        raise ValueError('Enter a Ghanaian or international phone number')
    return number


PhoneNumber = Annotated[str, Field(max_length=64), AfterValidator(require_phone_number)]
