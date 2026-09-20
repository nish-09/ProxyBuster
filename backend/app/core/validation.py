from typing import Annotated

import email_validator
from pydantic import AfterValidator


def _validate_email(value: str) -> str:
    # Plain pydantic EmailStr rejects RFC 2606 reserved test domains (example.com/.test/
    # .invalid/.localhost etc.) as "special-use" by default. That breaks the @example.test
    # convention used for seed/dev fake identities (see backend/seed.py), so validate with
    # test_environment=True to explicitly allow those — this only relaxes the reserved-TLD
    # heuristic, it does not accept malformed addresses or skip real syntax validation, and
    # is safe to leave on in production since no real institutional email uses those TLDs.
    email_validator.validate_email(value.strip(), test_environment=True, check_deliverability=False)
    # Emails are stored and compared lower-cased: phone keyboards auto-capitalise the first
    # letter, and "Asha@college.edu" must not be a different account from "asha@college.edu".
    return value.strip().lower()


# Drop-in replacement for pydantic.EmailStr used throughout the app's schemas.
EmailStr = Annotated[str, AfterValidator(_validate_email)]
