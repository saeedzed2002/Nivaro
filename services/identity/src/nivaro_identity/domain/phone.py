import re

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_phone(value: str) -> str:
    """Iran mobile domestic input, or explicit international E.164 syntax.

    Syntax is not a claim of carrier deliverability. The mock adapter restricts
    delivery to the operator's explicit test-number allowlist.
    """
    number = re.sub(r"[ ()-]", "", value.translate(_DIGITS).strip())
    if re.fullmatch(r"09[0-9]{9}", number):
        number = "+98" + number[1:]
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", number):
        raise ValueError("Use an international phone number including its country code")
    if number.startswith("+98") and not re.fullmatch(r"\+989[0-9]{9}", number):
        raise ValueError("An Iranian mobile number is required")
    return number
