"""Experimental optional adapter for a deliberately narrow Typer 0.27 leaf app.

Inspect static metadata, never parse arguments or invoke a callback. Keep this
adapter out of the package's public exports until the MVP9 integration release.
"""

import inspect
from types import FunctionType
from typing import Annotated, get_args, get_origin

from packaging.version import Version

from .command_contract import CommandContract, CommandOption


def from_typer(app, *, script, input_args=(), path_args=()):
    try:
        import typer
        from typer.core import TyperCommand
        from typer.main import get_command
        from typer.models import DefaultPlaceholder, OptionInfo
    except ImportError as error:
        raise ValueError('The experimental command adapter requires optional Typer 0.27.') from error
    version = Version(typer.__version__)
    if version.release[:2] != (0, 27):
        raise ValueError('Experimental adapter supports Typer 0.27 only; other versions need capability tests.')

    def setting(value):
        return value.value if type(value) is DefaultPlaceholder else value

    if type(app) is not typer.Typer:
        raise ValueError('Provide a plain Typer app.')
    if (app.registered_callback is not None or setting(app.info.callback) is not None
            or app.registered_groups or len(app.registered_commands) != 1 or app._add_completion
            or setting(app.info.context_settings) or setting(app.info.result_callback)
            or setting(app.info.chain) or setting(app.info.invoke_without_command)
            or setting(app.info.cls) is not None):
        raise ValueError('This proof requires one leaf command, no app callbacks/context overrides, and add_completion=False.')
    entry = app.registered_commands[0]
    callback = entry.callback
    if (entry.cls is not TyperCommand or entry.context_settings
            or type(callback) is not FunctionType or hasattr(callback, '__wrapped__')):
        raise ValueError('Custom command classes, contexts and wrapped callbacks are unsupported.')
    signature = inspect.signature(callback, follow_wrapped=False, eval_str=False)
    if signature.return_annotation not in (inspect.Signature.empty, None, type(None), int, float, str, bool):
        raise ValueError('Unsupported return annotation; forward annotation evaluation is disabled.')
    baseline = vars(typer.Option())
    allowed = {'default', 'param_decls', 'min', 'max', 'help', 'metavar', 'show_default', 'show_choices',
               'show_envvar', 'hidden', 'rich_help_panel'}
    definitions = []
    for parameter in signature.parameters.values():
        if parameter.kind not in (parameter.POSITIONAL_OR_KEYWORD, parameter.KEYWORD_ONLY):
            raise ValueError(f'{parameter.name}: variadic/positional-only arguments are unsupported.')
        annotation, information, annotated = parameter.annotation, None, False
        if get_origin(annotation) is Annotated:
            annotation, *metadata = get_args(annotation)
            if len(metadata) != 1 or type(metadata[0]) is not OptionInfo:
                raise ValueError(f'{parameter.name}: use one static Typer Option declaration.')
            information, annotated = metadata[0], True
        if type(parameter.default) is OptionInfo:
            if information is not None:
                raise ValueError(f'{parameter.name}: mixed Option declarations are unsupported.')
            information = parameter.default
        if annotation not in (str, int, float, bool):
            raise ValueError(f'{parameter.name}: only native scalar annotations are supported; no forward evaluation.')
        default = parameter.default
        if information is not None:
            for field, value in vars(information).items():
                if field not in allowed and (field not in baseline or value != baseline[field]):
                    raise ValueError(f'{parameter.name}: unsupported Typer option behavior: {field}.')
            if information.param_decls or (annotated and information.default is not Ellipsis):
                raise ValueError(f'{parameter.name}: custom flag declarations are unsupported in this proof.')
            if not annotated:
                default = information.default
        elif default is inspect.Parameter.empty:
            raise ValueError(f'{parameter.name}: declare required named options with typer.Option().')
        required = default is inspect.Parameter.empty or default is Ellipsis
        definitions.append(CommandOption(parameter.name, annotation.__name__, required,
                                         None if required else default,
                                         information.min if information else None,
                                         information.max if information else None))
    # Typer only sees prechecked static annotations/options here. In particular,
    # get_type_hints cannot evaluate strings or dynamic declarations from this app.
    command = get_command(app)
    if [parameter.name for parameter in command.params] != [option.name for option in definitions]:
        raise ValueError('Unsupported Typer metadata: command parameters changed during discovery.')
    for parameter, option in zip(command.params, definitions):
        if (parameter.opts != ['--' + parameter.name.replace('_', '-')]
                or parameter.callback is not None or parameter.nargs != 1 or parameter.multiple
                or parameter.required != option.required
                or bool(parameter.is_flag) != (option.kind == 'bool')
                or (option.kind == 'bool' and (not parameter.is_bool_flag or parameter.default is not False))):
            raise ValueError(f'{parameter.name}: unsupported parser semantics.')
    return CommandContract(script, tuple(definitions), tuple(input_args), tuple(path_args))
