"""Argument grammar and help for the ``ret`` command.

Keep command discovery and shell completion tied to the same argparse
subparsers, so a newly registered command appears in both places.
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
    'init', 'run', 'status', 'pack', 'pull', 'export', 'import',
    'verify', 'audit', 'assess', 'rebuild', 'crosscheck', 'record', 'sign',
)

# Short, still useful spellings. Retired command names are deliberately absent;
# their former uses are options on the corresponding porcelain commands.
ALIASES = {'ls': 'status', 'check': 'verify', 'redo': 'rebuild'}

_FULL_HELP = {
    'init': 'Initialize a workspace and wire its agent hooks.',
    'run': 'Run a command in a workspace and record its execution.',
    'status': 'Show the current workspace, claims, or directory tree.',
    'pack': 'Create and seal a claim from project files.',
    'pull': 'Add the contents of a claim to a workspace.',
    'export': 'Write a portable archive of a sealed claim.',
    'import': 'Restore and verify a portable claim archive.',
    'verify': 'Check the sealed identity against present pinned bytes.',
    'audit': 'Rerun acceptance criteria in a fresh judging room.',
    'assess': 'Measure the strength of a claim’s acceptance criteria.',
    'rebuild': 'Recreate generated outputs from pinned inputs.',
    'crosscheck': 'Compare original, transfer, and independent rebuild.',
    'record': 'Write or check a portable execution record.',
    'sign': 'Authorize a claim or check its authorization.',
    'hook': 'Receive an agent hook event.',
    'help': 'Show command help.',
    'completion': 'Print shell completion generated from the command grammar.',
}


def _add_verbose_json(command_parser: argparse.ArgumentParser) -> None:
    """Give action commands the two common presentation switches."""
    command_parser.add_argument('-v', '--verbose', action='store_true',
                                help='show additional details')
    command_parser.add_argument('--json', action='store_true',
                                help='write a JSON result')


def _parser():
    """Return the top-level parser and its command parsers."""
    parser = argparse.ArgumentParser(
        prog='ret', description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--version', action='store_true', help='show version')
    commands = parser.add_subparsers(dest='command', metavar='<command>')
    topics = {}

    def add(name, summary):
        aliases = [alias for alias, target in ALIASES.items() if target == name]
        child = commands.add_parser(name, aliases=aliases, help=summary,
                                    description=_FULL_HELP[name])
        _add_verbose_json(child)
        topics[name] = child
        for alias in aliases:
            topics[alias] = child
        return child

    p = add('init', 'initialize a workspace')
    p.add_argument('workspace', nargs='?', default='.')
    p.add_argument('--no-agent', action='store_true', help='skip agent hook setup')

    p = add('run', 'run and observe a command')
    p.add_argument('command_line', nargs=argparse.REMAINDER, metavar='command')
    p.add_argument('-C', '--workspace', default='.')

    p = add('status', 'show work, claims, and unresolved inputs')
    p.add_argument('path', nargs='?', default='.')
    view = p.add_mutually_exclusive_group()
    view.add_argument('--tree', action='store_true', help='show directory structure')
    view.add_argument('--claims', action='store_true', help='list claims')
    view.add_argument('--deps', action='store_true', help='show dependencies')

    p = add('pack', 'create a claim from a project')
    p.add_argument('root', nargs='?', default='.')
    p.add_argument('--name', required=True)
    p.add_argument('--generated', action='append', default=[])
    p.add_argument('--input', dest='inputs', action='append', default=[])
    p.add_argument('--gate', required=True)
    p.add_argument('--gate-output', required=True)
    p.add_argument('--accept', action='store_true', help='seal the resulting claim')
    p.add_argument('--inputs-manifest')
    p.add_argument('--environment')

    p = add('pull', 'add another claim as a dependency')
    p.add_argument('claim')
    p.add_argument('workspace', nargs='?', default='.')

    p = add('export', 'write a portable claim archive')
    p.add_argument('claim')
    p.add_argument('archive')
    p.add_argument('--blind', action='store_true')

    p = add('import', 'restore a claim archive')
    p.add_argument('archive')
    p.add_argument('into')

    p = add('verify', 'verify claim identity')
    p.add_argument('claim', nargs='?', default='.')

    p = add('audit', 'rerun acceptance criteria')
    p.add_argument('claim', nargs='?', default='.')
    p.add_argument('--shallow', action='store_true')

    p = add('assess', 'measure specification strength')
    p.add_argument('claim', nargs='?', default='.')
    p.add_argument('--mutants', type=int, default=20)

    p = add('rebuild', 'rebuild an implementation from a claim')
    p.add_argument('claim')
    p.add_argument('into')
    p.add_argument('--producer', required=True)
    p.add_argument('--without-guidance', action='store_true')

    p = add('crosscheck', 'compare independent realizations')
    p.add_argument('original')
    p.add_argument('transfer')
    p.add_argument('rebuild')
    p.add_argument('--mutants', type=int)

    p = add('record', 'write an execution record')
    p.add_argument('claim', nargs='?', default='.')
    p.add_argument('--output')
    p.add_argument('--key')
    p.add_argument('--as', dest='identity')
    p.add_argument('--check', action='store_true')

    p = add('sign', 'authorize a claim or proof')
    p.add_argument('claim', nargs='?', default='.')
    p.add_argument('--key')
    p.add_argument('--as', dest='identity')
    p.add_argument('--check', action='store_true')

    p = commands.add_parser('hook', help='receive an agent hook event',
                            description=_FULL_HELP['hook'])
    topics['hook'] = p

    p = commands.add_parser('help', help='show help for a command',
                            description=_FULL_HELP['help'])
    p.add_argument('topic', nargs='?')
    p.add_argument('-a', '--all', action='store_true',
                   help='include every command and accepted alias')
    topics['help'] = p

    p = commands.add_parser('completion', help='print shell completion',
                            description=_FULL_HELP['completion'])
    p.add_argument('shell', choices=('bash', 'zsh', 'fish'))
    topics['completion'] = p
    return parser, topics


def verbs():
    """Return all accepted first-position command words."""
    _, topics = _parser()
    return tuple(topics)


def _help_topic(topic):
    parser, topics = _parser()
    if topic is None:
        print(parser.format_help(), end='')
    elif topic in topics:
        print(topics[topic].format_help(), end='')
        canonical = ALIASES.get(topic, topic)
        detail = _FULL_HELP.get(canonical)
        if detail:
            print('\n' + detail)
    else:
        parser.error(f'unknown help topic: {topic}')


def _help_all():
    parser, topics = _parser()
    print(parser.format_help(), end='')
    for name in PORCELAIN + ('hook', 'help', 'completion'):
        print(f'\n{name}\n{topics[name].format_help()}', end='')
    if ALIASES:
        print('\nAccepted older spellings:')
        for alias, target in ALIASES.items():
            print(f'  {alias} → {target}')


def _completion(shell):
    """Print completion words read from the registered subparsers."""
    _, topics = _parser()
    words = ' '.join(topics)
    if shell == 'bash':
        print(f'_ret_complete() {{ COMPREPLY=( $(compgen -W "{words}" -- "${{COMP_WORDS[COMP_CWORD]}}") ); }}')
        print('complete -F _ret_complete ret')
    elif shell == 'zsh':
        print(f'#compdef ret\n_arguments "1:command:({words})"')
    elif shell == 'fish':
        for word in topics:
            print(f'complete -c ret -f -n "__fish_use_subcommand" -a "{word}"')
    else:
        raise ValueError(f'unsupported shell: {shell}')
