"""Run once with python -m tools.setup_admin from the backend directory."""
from getpass import getpass

from pydantic import ValidationError

from app.administration import bootstrap_admin
from app.main import AdminRegister, SessionLocal


def main():
    name = input('Administrator full name: ')
    email = input('Administrator email: ')
    password = getpass('Administrator password: ')
    if password != getpass('Confirm administrator password: '):
        raise SystemExit('Passwords differ')
    try:
        data = AdminRegister(full_name=name, email=email, password=password)
    except ValidationError as exc:
        fields = ', '.join(str(error['loc'][0]) for error in exc.errors())
        raise SystemExit(f'Invalid administrator fields: {fields}') from None
    with SessionLocal() as db:
        try:
            bootstrap_admin(data, db)
        except ValueError as exc:
            raise SystemExit(str(exc)) from None
    print('First platform administrator created.')


if __name__ == '__main__':
    main()
