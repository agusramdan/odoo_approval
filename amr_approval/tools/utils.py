from functools import wraps

import logging
import inspect
import traceback
import base64
import binascii

from odoo import models

_logger = logging.getLogger(__name__)


def have_method(obj, method):
    return method and isinstance(method, str) and hasattr(obj, method) and callable(getattr(obj, method))


def save_call_method(obj, method_name, **kw):
    """
    Memanggil method pada object secara aman.
    Deprecated gunakan safe_call_method
    """
    return safe_call_method(obj, method_name, kwargs=kw)


def safe_call_method(obj, method_name, args=None, kwargs=None):
    """
    Memanggil method pada object secara aman.

    - method optional
    - method_name harus string
    - method harus callable
    - args disesuaikan dengan signature
    """
    if not obj and not isinstance(obj, models.BaseModel):
        _logger.warning(f"Object not eligible process {obj}")
        return None

    if not method_name or not isinstance(method_name, str):
        _logger.warning(f"Object not eligible process {obj}")
        return None

    if not hasattr(obj, method_name):
        _logger.warning(f"Method {method_name} not found")
        return None

    method = getattr(obj, method_name, None)
    if not callable(method):
        _logger.warning(f"Callable method '{method_name}' not found on {obj}")
        return None

    # === signature aware ===
    sig = inspect.signature(method)
    params = sig.parameters

    final_args = []
    final_kwargs = {}
    kwargs = dict(kwargs or {})
    args = list(args or [])
    for name, p in params.items():
        if p.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD
        ):
            if args:
                final_args.append(args[0])
                args = args[1:]
            elif name in kwargs:
                final_args.append(kwargs[name])
                # _logger.info(f"index {len(final_args)} from {name}")
                kwargs.pop(name)
            elif p.default is not inspect.Parameter.empty:
                # _logger.info(f"index {len(final_args)} default {p.default}")
                final_args.append(p.default)
            else:
                raise TypeError(f"Missing required argument: {name}")

        elif p.kind == inspect.Parameter.VAR_POSITIONAL:
            _logger.info(f"VAR_POSITIONAL {name}")
            final_args.extend(args)
            args = ()

        elif p.kind == inspect.Parameter.KEYWORD_ONLY:
            if name in kwargs:
                final_kwargs[name] = kwargs[name]
            elif p.default is inspect.Parameter.empty:
                raise TypeError(f"Missing keyword-only argument: {name}")

        elif p.kind == inspect.Parameter.VAR_KEYWORD:
            final_kwargs.update(kwargs)

    return method(*final_args, **final_kwargs)


def convert_to_tuple_create(input):
    if isinstance(input, tuple):
        return input
    if isinstance(input, dict):
        return (0, 0, input)


def ensure_dict(input):
    if isinstance(input, dict):
        return input
    else:
        return input.prepare_line_dict()


def ensure_list_create(record_list):
    return [ensure_dict(rec) for rec in record_list]


def call_retry(_func=None, *, callback_error_method_name=None, ):
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            _logger.info(f"Function in {func.__qualname__}")
            self.ensure_one()
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                _logger.error(f"Error in {func.__qualname__}: {str(e)}", exc_info=True)
                error_message = traceback.format_exc()
                res_method = func.__name__
                api_call_retry_id = self.env.context.get('__api_call_retry_id')
                if api_call_retry_id:
                    api_call_retry = self.env['api.call.retry'].browse(api_call_retry_id)
                else:
                    api_call_retry = self.env['api.call.retry']

                api_call_retry.need_retry(
                    self._name, self.id, res_method=res_method,
                    error_message=error_message, param_args=args, param_kwargs=kwargs
                )

                if callback_error_method_name and have_method(self, callback_error_method_name):
                    return safe_call_method(self, callback_error_method_name, [], {
                        'args': args,
                        'res_method': res_method,
                        'exception': e,
                        'kwargs': kwargs
                    })
                return

        return wrapper

    if _func is None:
        return decorator
    else:
        return decorator(_func)


def is_base64_bytes(b):
    if not isinstance(b, bytes):
        return False
    try:
        base64.b64decode(b, validate=True)
        return True
    except Exception:
        return False


def is_base64_string(s):
    if not isinstance(s, str):
        return False
    try:
        base64.b64decode(s, validate=True)
        return True
    except (binascii.Error, ValueError):
        return False


def normalize_binary(value):
    """
    Return base64 string or False
    """
    if not value:
        return False

    # sudah base64 string
    if isinstance(value, str) and is_base64_string(value):
        return value

    # binary bytes → convert ke base64
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(value).decode('utf-8')

    raise ValueError("Unsupported binary format")


def serialize_filter(self, for_default=False):
    self.ensure_one()
    data = {}

    for field_name, field in self._fields.items():
        value = getattr(self, field_name)
        key = f"default_{field_name}" if for_default else field_name
        if field.type == 'many2many':
            data[key] = (6, 0, value.ids) if value else []
        elif field.type == 'many2one':
            data[key] = value.id if value else None
        elif field.type == 'one2many':
            data[key] = [
                {k: getattr(line, k) for k in line._fields if k != 'id'}
                for line in value
            ]
        else:
            data[key] = value

    return data
