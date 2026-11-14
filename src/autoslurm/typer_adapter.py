"""Optional public adapter for a deliberately narrow Typer 0.27 leaf app.

Inspect static metadata, never parse arguments or invoke a callback.
"""

from .errors import InvalidRequestError, DiagnosticCause

import inspect
from types import FunctionType
from typing import Annotated, get_args, get_origin

from packaging.version import Version

from .command_contract import CommandContract, CommandOption

__all__ = ['from_typer']


def from_typer(app, *, script, input_args=(), path_args=()):
    """Derive a contract from one trusted, already-imported static leaf app.

    Install autoslurm[commands] on the authoring machine. Application execution
    needs only its own CLI; this function never imports a command by name.
    """
    try:
        import typer
        from typer.core import TyperCommand
        from typer.main import get_command
        from typer.models import DefaultPlaceholder, OptionInfo
    except ImportError as error:
        raise InvalidRequestError('The command adapter requires optional Typer 0.27; install autoslurm[commands].',
            field='typer', stage='derive_command', cause=DiagnosticCause.from_exception(error)) from error
    version = Version(typer.__version__)
    if version.release[:2] != (0, 27):
        raise InvalidRequestError(f'Installed Typer {version} is unsupported. The adapter supports Typer 0.27 only; other versions need capability tests.', field='typer', stage='derive_command')

    def setting(value):
        return value.value if type(value) is DefaultPlaceholder else value

    if type(app) is not typer.Typer:
        raise InvalidRequestError('Provide a plain Typer app.', field='app', stage='derive_command')
    if (app.registered_callback is not None or setting(app.info.callback) is not None
            or app.registered_groups or len(app.registered_commands) != 1 or app._add_completion
            or setting(app.info.context_settings) or setting(app.info.result_callback)
            or setting(app.info.chain) or setting(app.info.invoke_without_command)
            or setting(app.info.cls) is not None):
        raise InvalidRequestError('The adapter requires one leaf command, no app callbacks/context overrides, and add_completion=False.', field='app', stage='derive_command')
    entry = app.registered_commands[0]
    callback = entry.callback
    if (entry.cls is not TyperCommand or entry.context_settings
            or type(callback) is not FunctionType or hasattr(callback, '__wrapped__')):
        raise InvalidRequestError('Custom command classes, contexts and wrapped callbacks are unsupported.', field='callback', stage='derive_command')
    signature = inspect.signature(callback, follow_wrapped=False, eval_str=False)
    if signature.return_annotation not in (inspect.Signature.empty, None, type(None), int, float, str, bool):
        raise InvalidRequestError('Unsupported return annotation; forward annotation evaluation is disabled.', field='return_annotation', stage='derive_command')
    baseline = vars(typer.Option())
    allowed = {'default', 'param_decls', 'min', 'max', 'help', 'metavar', 'show_default', 'show_choices',
               'show_envvar', 'hidden', 'rich_help_panel'}
    definitions = []
    for parameter in signature.parameters.values():
        if parameter.kind not in (parameter.POSITIONAL_OR_KEYWORD, parameter.KEYWORD_ONLY):
            raise InvalidRequestError(f'{parameter.name}: variadic/positional-only arguments are unsupported.', field='options', context={'option': parameter.name}, stage='derive_command')
        annotation, information, annotated = parameter.annotation, None, False
        if get_origin(annotation) is Annotated:
            annotation, *metadata = get_args(annotation)
            if len(metadata) != 1 or type(metadata[0]) is not OptionInfo:
                raise InvalidRequestError(f'{parameter.name}: use one static Typer Option declaration.', field='options', context={'option': parameter.name}, stage='derive_command')
            information, annotated = metadata[0], True
        if type(parameter.default) is OptionInfo:
            if information is not None:
                raise InvalidRequestError(f'{parameter.name}: mixed Option declarations are unsupported.', field='options', context={'option': parameter.name}, stage='derive_command')
            information = parameter.default
        if annotation not in (str, int, float, bool):
            raise InvalidRequestError(f'{parameter.name}: only native scalar annotations are supported; no forward evaluation.', field='options', context={'option': parameter.name}, stage='derive_command')
        default = parameter.default
        if information is not None:
            for field, value in vars(information).items():
                if field not in allowed and (field not in baseline or value != baseline[field]):
                    raise InvalidRequestError(f'{parameter.name}: unsupported Typer option behavior: {field}.', field='options', context={'option': parameter.name}, stage='derive_command')
            if information.param_decls or (annotated and information.default is not Ellipsis):
                raise InvalidRequestError(f'{parameter.name}: custom flag declarations are unsupported.', field='options', context={'option': parameter.name}, stage='derive_command')
            if not annotated:
                default = information.default
        elif default is inspect.Parameter.empty:
            raise InvalidRequestError(f'{parameter.name}: declare required named options with typer.Option().', field='options', context={'option': parameter.name}, stage='derive_command')
        required = default is inspect.Parameter.empty or default is Ellipsis
        definitions.append(CommandOption(parameter.name, annotation.__name__, required,
                                         None if required else default,
                                         information.min if information else None,
                                         information.max if information else None))
    # Typer only sees prechecked static annotations/options here. In particular,
    # get_type_hints cannot evaluate strings or dynamic declarations from this app.
    command = get_command(app)
    if [parameter.name for parameter in command.params] != [option.name for option in definitions]:
        raise InvalidRequestError('Unsupported Typer metadata: command parameters changed during discovery.', field='options', stage='derive_command')
    for parameter, option in zip(command.params, definitions):
        if (parameter.opts != ['--' + parameter.name.replace('_', '-')]
                or parameter.callback is not None or parameter.nargs != 1 or parameter.multiple
                or parameter.required != option.required
                or bool(parameter.is_flag) != (option.kind == 'bool')
                or (option.kind == 'bool' and (not parameter.is_bool_flag or parameter.default is not False))):
            raise InvalidRequestError(f'{parameter.name}: unsupported parser semantics.', field='options', context={'option': parameter.name}, stage='derive_command')
    return CommandContract(script, tuple(definitions), input_args, path_args)
