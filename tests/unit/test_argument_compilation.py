"""Literal argv and shell output agree without machine or parser dependencies."""

import json
import shlex
import subprocess
import sys

import pytest

from autoslurm.argument_compilation import compile_script_arguments, render_script_arguments


def test_plain_output_and_legacy_omission_are_unchanged():
    arguments = {'label': 'trial', 'repeat': 2, 'offset': -0.5, 'enabled': True,
                 'disabled': False, 'absent': None, 'empty': [], 'values': [1, 2, 3],
                 '__positionals__': ['input.json']}
    groups = compile_script_arguments(arguments)
    assert groups == (('--label=trial',), ('--repeat=2',), ('--offset=-0.5',),
                      ('--enabled',), ('--values', '1', '2', '3'), ('input.json',))
    assert render_script_arguments(groups) == ['  --label=trial', '  --repeat=2',
        '  --offset=-0.5', '  --enabled', '  --values 1 2 3', '  input.json']
    assert compile_script_arguments({}) == ()
    assert arguments['values'] == [1, 2, 3]


@pytest.mark.parametrize('value', [
    'two words', "a'b", 'a"b', '$HOME', '${SLURM_ARRAY_TASK_ID}', '$(touch injected)',
    '`touch injected`', 'x; touch injected', '*?[abc]', '--other=value', 'a=b', '', 'étoile α',
])
def test_each_scalar_is_one_literal_argument(value):
    groups = compile_script_arguments({'my_label': value})
    assert groups == ((f'--my-label={value}',),)
    assert shlex.split('\n'.join(render_script_arguments(groups))) == [f'--my-label={value}']


def test_raw_list_elements_and_positionals_are_separately_quoted():
    groups = compile_script_arguments({'values': ['two words', "a'b", '$HOME', 2, True],
                                      '__positionals__': ['x; echo y', '', '*.json']})
    assert groups == (('--values', 'two words', "a'b", '$HOME', '2', 'True'),
                      ('x; echo y',), ('',), ('*.json',))
    assert shlex.split('\n'.join(render_script_arguments(groups))) == [token for group in groups for token in group]


@pytest.mark.local_processes
def test_shell_executes_compiled_tokens_without_expansion(tmp_path):
    (tmp_path / 'glob.json').write_text('[]')
    before = set(tmp_path.iterdir())
    groups = compile_script_arguments({
        'label': "trial's $(touch injected) `touch injected-too`; $HOME *",
        'parts': ['*.json', 'two words', '$(touch list-injected)', ''],
        '__positionals__': ['${SLURM_ARRAY_TASK_ID}', 'x; touch positional-injected', ''],
    })
    command = shlex.quote(sys.executable) + ' -c ' + shlex.quote('import json, sys; print(json.dumps(sys.argv[1:]))')
    script = command + ' \\\n' + ' \\\n'.join(render_script_arguments(groups)) + '\n'
    result = subprocess.run(['bash', '-c', script], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [token for group in groups for token in group]
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize('arguments,match', [
    ([], 'mapping'), ({'bad;name': 1}, 'option name'), ({'two words': 1}, 'option name'),
    ({'--flag': 1}, 'option name'), ({2: 'value'}, 'option name'),
    ({'same_name': 1, 'same-name': 2}, 'Duplicate'),
    ({'value': {'hidden': 1}}, 'value.*scalar'), ({'value': (1, 2)}, 'value.*scalar'),
    ({'value': float('nan')}, 'finite'), ({'value': float('inf')}, 'finite'),
    ({'value': 'a\nb'}, 'control'), ({'value': '\x00'}, 'control'),
    ({'value': '\t'}, 'control'), ({'value': '\x7f'}, 'control'),
    ({'items': [[1]]}, r'items\[0\].*scalar'), ({'items': [None]}, r'items\[0\].*scalar'),
    ({'__positionals__': 'one string'}, '__positionals__.*list'),
    ({'__positionals__': [{'hidden': 2}]}, '__positionals__.*scalar'),
])
def test_invalid_arguments_fail_with_the_setting_name(arguments, match):
    with pytest.raises(ValueError, match=match):
        compile_script_arguments(arguments)
