"""Argument grammar and help for the ``ret`` command.

Keep command registration in one place so help, verb discovery, and shell
completion describe the same interface.
"""

from __future__ import annotations

import argparse


_DESC = ('Reticuli records and reproduces software claims.\n\n'
         'Authoring\n'
         '    init        initialize a workspace\n'
         '    run         run and observe a command\n'
         '    status      show work, claims, and unresolved inputs\n'
         '    pack        create a claim from a project\n\n'
         'Composition and transport\n'
         '    pull        add another claim as a dependency\n'
         '    export      write a portable claim archive\n'
         '    import      restore a claim archive\n\n'
         'Verification\n'
         '    verify      verify claim identity\n'
         '    audit       rerun acceptance criteria\n'
         '    assess      measure specification strength\n\n'
         'Reconstruction\n'
         '    rebuild     rebuild an implementation from a claim\n'
         '    crosscheck  compare independent realizations\n\n'
         'Evidence\n'
         '    record      write an execution record\n'
         '    sign        authorize a claim or proof')

_EPILOG = ("See 'ret <command> -h' for command usage.\n"
           "See 'ret help <command>' for detailed help; 'ret help -a' lists everything,\n"
           'including accepted older spellings.')

PORCELAIN = (
    'init', 'run', 'status', 'pack',
    'pull', 'export', 'import',
    'verify', 'audit', 'assess',
    'rebuild', 'crosscheck',
    'record', 'sign',
)

# Short, non-retired spelling retained for scripts that list workspace claims.
ALIASES = {'ls': 'status'}

_FULL_HELP = {
    'init': 'Initialize a workspace and install the agent hook unless --no-agent is set.',
    'run': 'Run a shell command in the workspace and observe the session.',
    'status': 'Show a workspace or claim, its dependencies, and the next useful action.',
    'pack': 'Create and seal a claim from declared generated files, inputs, and a gate.',
    'pull': 'Bring another claim into the workspace as a dependency.',
    'export': 'Write a portable archive of a claim.',
    'import': 'Restore and verify a portable claim archive.',
    'verify': 'Compare present pinned bytes with a sealed root without running gates.',
    'audit': 'Rerun acceptance gates to earn a current verdict.',
    'assess': 'Measure how strongly the gates constrain generated files.',
    'rebuild': 'Regrow generated files from pinned inputs using a producer.',
    'crosscheck': 'Compare original, transferred, and independent realizations.',
    'record': 'Write or check a signed record of an earned result.',
    'sign': 'Authorize a claim or check an existing authorization.',
    'hook': 'Consume an agent hook event from standard input.',
    'help': 'Show command help.',
    'completion': 'Print shell completion generated from registered commands.',
}


def _add_verbose_json(command: argparse.ArgumentParser) -> None:
    """Add the common presentation switches to a command parser."""
    command.add_argument('-v', '--verbose', action='store_true',
                         help='show supporting details')
    command.add_argument('--json', action='store_true',
                         help='write a JSON result')


def _parser() -> tuple[argparse.ArgumentParser, dict[str, argparse.ArgumentParser]]:
    """Build the CLI grammar and return the parser with its command parsers."""
    parser = argparse.ArgumentParser(
        prog='ret', description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', action='version', version='reticuli')
    sub = parser.add_subparsers(dest='command', metavar='command')
    commands: dict[str, argparse.ArgumentParser] = {}

    def add(name: str, *, summary: str | None = None) -> argparse.ArgumentParser:
        child = sub.add_parser(name, help=summary or _FULL_HELP[name],
                               description=_FULL_HELP.get(name, summary))
        commands[name] = child
        if name not in ('help', 'completion', 'hook'):
            _add_verbose_json(child)
        return child

    p = add('init')
    p.add_argument('workspace', nargs='?', default='.')
    p.add_argument('--no-agent', action='store_true')

    p = add('run')
    p.add_argument('shell_command', nargs=argparse.REMAINDER)
    p.add_argument('-C', '--workspace', default='.')

    p = add('status')
    p.add_argument('path', nargs='?', default='.')
    for flag in ('tree', 'claims', 'deps', 'files'):
        p.add_argument('--' + flag, action='store_true')

    p = add('pack')
    p.add_argument('path', nargs='?', default='.')
    p.add_argument('--name', required=True)
    p.add_argument('--generated', action='append', default=[])
    p.add_argument('--input', action='append', default=[])
    p.add_argument('--gate', required=True)
    p.add_argument('--gate-output', required=True)
    p.add_argument('--inputs-manifest')
    p.add_argument('--environment')
    p.add_argument('--format', type=int, dest='claim_format', default=3)
    p.add_argument('--mutation-floor', type=float)
    p.add_argument('--requires', action='append', default=[])
    p.add_argument('--by')
    p.add_argument('--accept', action='store_true')

    p = add('pull')
    p.add_argument('claim')
    p.add_argument('workspace', nargs='?', default='.')

    p = add('export')
    p.add_argument('claim')
    p.add_argument('archive')
    p.add_argument('--blind', action='store_true')

    p = add('import')
    p.add_argument('archive')
    p.add_argument('into')

    p = add('verify')
    p.add_argument('claim', nargs='?', default='.')

    p = add('audit')
    p.add_argument('claim', nargs='?', default='.')
    p.add_argument('--shallow', action='store_true')

    p = add('assess')
    p.add_argument('claim', nargs='?', default='.')
    p.add_argument('--mutants', type=int, default=100)

    p = add('rebuild')
    p.add_argument('claim')
    p.add_argument('--producer', required=True)
    p.add_argument('--into', required=True)
    p.add_argument('--without-guidance', action='store_true')
    p.add_argument('--reuse', action='store_true')

    p = add('crosscheck')
    for leg in ('m1', 'm2', 'm3'):
        p.add_argument(leg)
    p.add_argument('--record', action='store_true')
    p.add_argument('--mutants', type=int)

    p = add('record')
    p.add_argument('claim', nargs='?', default='.')
    p.add_argument('--output')
    p.add_argument('--key')
    p.add_argument('--as', dest='identity')
    p.add_argument('--check', action='store_true')
    p.add_argument('--signers')

    p = add('sign')
    p.add_argument('claim', nargs='?', default='.')
    p.add_argument('--key')
    p.add_argument('--as', dest='identity')
    p.add_argument('--check', action='store_true')
    p.add_argument('--signers')

    p = add('hook')
    p.add_argument('event', nargs='?')

    p = add('help')
    p.add_argument('topic', nargs='?')
    p.add_argument('-a', '--all', action='store_true')

    p = add('completion')
    p.add_argument('shell', choices=('bash', 'zsh', 'fish'), nargs='?', default='bash')

    for alias, target in ALIASES.items():
        p = add(alias, summary=f'alias for {target}')
        p.add_argument('path', nargs='?', default='.')

    return parser, commands


def verbs() -> tuple[str, ...]:
    """Return the registered command names in grammar order."""
    _, commands = _parser()
    return tuple(commands)


def _help_topic(topic: str) -> None:
    parser, commands = _parser()
    if topic not in commands:
        parser.error(f'unknown help topic: {topic}')
    commands[topic].print_help()


def _help_all() -> None:
    parser, commands = _parser()
    parser.print_help()
    for name in commands:
        print('\n' + name)
        commands[name].print_help()


def _completion(shell: str = 'bash') -> None:
    """Print completion words drawn from the parser's registered verbs."""
    words = ' '.join(verbs())
    if shell == 'bash':
        print(f'_ret_complete() {{ COMPREPLY=( $(compgen -W "{words}" -- "${{COMP_WORDS[COMP_CWORD]}}") ); }}')
        print('complete -F _ret_complete ret')
    elif shell == 'zsh':
        print(f'#compdef ret\n_arguments "1:command:({words})"')
    elif shell == 'fish':
        for name in verbs():
            print(f'complete -c ret -f -a {name}')
    else:
        raise ValueError(f'unsupported completion shell: {shell}')
