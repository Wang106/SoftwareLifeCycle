"""Run with python -m app.admin_operator; disabled by default, never at startup."""
import argparse
import json
from pathlib import Path
import sys

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import SessionLocal
from app.services.admin_operator import BootstrapAdmin, RecoverAdmin, OperatorError, apply, plan, preconditions


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise OperatorError('invalid_operator_arguments')


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument('operation', choices=['plan', 'bootstrap', 'recover'])
    parser.add_argument('--request', type=Path, help='Reviewed JSON request file for mutation')
    try:
        args = parser.parse_args(argv)
        preconditions()
        if args.operation == 'plan':
            if args.request is not None:
                raise OperatorError('plan_has_no_request')
            body = None
        else:
            if args.request is None:
                raise OperatorError('operator_request_required')
            # Never echo validation input, identity references, DSN or stack traces.
            with args.request.open("rb") as stream:
                content = stream.read(16385)
            if len(content) > 16384:
                raise OperatorError('operator_request_too_large')
            model = BootstrapAdmin if args.operation == 'bootstrap' else RecoverAdmin
            body = model.model_validate_json(content)
        with SessionLocal() as db:
            if db.get_bind().dialect.name != 'postgresql':
                raise OperatorError('operator_postgresql_required')
            result = plan(db) if body is None else apply(db, body)
        print(json.dumps(result, default=str, ensure_ascii=False))
        return 0
    except OperatorError as exc:
        error = str(exc)
    except (ValidationError, OSError, UnicodeError):
        error = 'invalid_operator_request'
    except SQLAlchemyError:
        error = 'operator_database_unavailable'
    except Exception:
        error = 'operator_failed'
    print(json.dumps({'error': error}), file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
