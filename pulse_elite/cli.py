import argparse
import json
from pathlib import Path
import sys
from . import __version__, core


class HelpFormatter(argparse.HelpFormatter):
    def _format_action(self, action):
        if isinstance(action, argparse._SubParsersAction):
            return ''.join(self._format_action(command) for command in action._get_subactions())
        return super()._format_action(action)


class HelpParser(argparse.ArgumentParser):
    """Show available arguments for an unfinished command; reject invalid input."""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('formatter_class', HelpFormatter)
        super().__init__(*args, **kwargs)
        self._positionals.title = 'arguments'

    def error(self, message):
        if 'the following arguments are required:' in message or 'expected one argument' in message:
            self.print_help()
            self.exit(0)
        super().error(message)


def question_help(root, words):
    """Resolve a help-only command path without executing any command."""
    current = root
    index = 0
    while index < len(words):
        word = words[index]
        option = current._option_string_actions.get(word)
        if option is not None:
            index += 1 if option.nargs == 0 else 2
            continue
        sub = next((a for a in current._actions if isinstance(a, argparse._SubParsersAction)), None)
        if sub is not None and word in sub.choices:
            current = sub.choices[word]
        else:
            current.error('unrecognized argument: ' + word)
        index += 1
    current.print_help()


def parser():
    p = HelpParser(prog='ps-pulse', description='PS-Pulse: automatic headset audio switching')
    p.add_argument('--version', action='version', version=__version__)
    p.add_argument('--config', type=Path, help='Custom config for foreground use; service uses the default path')
    sub = p.add_subparsers(dest='action', required=True)
    for name in ('devices', 'status', 'show-config'):
        sub.add_parser(name, help={'devices': 'List available audio outputs', 'status': 'Show switching and headset status', 'show-config': 'Show selected output devices'}[name]).add_argument('--json', action='store_true', help='Print full machine-readable JSON')
    configure = sub.add_parser('configure', help='Pick outputs interactively or provide their node names')
    configure.add_argument('--headset', default='auto', metavar='NODE', help='Headset output node (default: automatic detection)')
    configure.add_argument('--fallback', metavar='NODE', help='Output to use when the headset disconnects')
    configure.add_argument('--json', action='store_true', help='Print full machine-readable JSON')
    for name, help_text in (('start', 'Start automatic switching'), ('stop', 'Stop automatic switching'),
                            ('restart', 'Restart automatic switching')):
        sub.add_parser(name, help=help_text).add_argument('--json', action='store_true', help='Print full machine-readable JSON')
    autostart = sub.add_parser('autostart', help='Control automatic startup at login')
    settings = autostart.add_subparsers(dest='setting', required=True)
    for name, text in (('enable', 'Start switching automatically at login'),
                       ('disable', 'Do not start switching automatically at login')):
        settings.add_parser(name, help=text).add_argument('--json', action='store_true', help='Print full machine-readable JSON')
    for name in ('run', 'dry-run'):
        cmd = sub.add_parser(name, help='Run switching in the foreground' if name == 'run' else 'Preview routing without changing outputs')
        cmd.add_argument('--duration', type=float, help='Stop after this many seconds')
    sub.add_parser('gui', help='Open the optional desktop setup window')
    sub.add_parser('migrate', help='Back up and retire the previous manual installation after package installation')
    return p


def choose(available, headset, fallback):
    candidates = [s for s in available if s['is_headset']]
    if headset == 'auto':
        if len(candidates) != 1:
            raise core.AppError('Connect one supported adapter and activate its audio output, or specify --headset.')
        headset = candidates[0]['name']
    if not fallback:
        if not sys.stdin.isatty():
            raise core.AppError('Noninteractive setup requires --fallback NODE_NAME. Use devices --json to list outputs.')
        options = [s for s in available if not s['is_headset']]
        if not options:
            raise core.AppError('No fallback outputs found.')
        for i, s in enumerate(options, 1):
            print(f"{i}. {s['label']}")
        try:
            number = int(input('Fallback output number: '))
            if not 1 <= number <= len(options):
                raise ValueError()
            fallback = options[number - 1]['name']
        except (ValueError, EOFError):
            raise core.AppError('Choose a valid output number.')
    return core.make_config(headset, fallback, available)



def main(argv=None):
    words = list(sys.argv[1:] if argv is None else argv)
    root = parser()
    if words and words[-1] == '?':
        question_help(root, words[:-1])
        return 0
    args = root.parse_args(words)
    try:
        result = None
        if args.action == 'devices':
            result = core.sinks()
        elif args.action == 'status':
            result = core.status(args.config)
        elif args.action == 'show-config':
            result = core.load_config(args.config)
        elif args.action == 'configure':
            if args.json and not args.fallback:
                raise core.AppError('--json configuration requires --fallback.')
            result = choose(core.sinks(), args.headset, args.fallback)
            core.atomic_json(args.config or core.config_path(), result)
        elif args.action in ('run', 'dry-run'):
            if args.duration is not None and args.duration <= 0:
                raise core.AppError('Duration must be positive.')
            from .daemon import run
            run(args.config, args.action == 'dry-run', args.duration)
        elif args.action == 'gui':
            if args.config:
                raise core.AppError('The desktop UI uses the default configuration path.')
            try:
                from .gui import launch
            except ImportError:
                raise core.AppError('Install ps-pulse-desktop to use the UI.')
            launch()
        elif args.action == 'migrate':
            result = core.migrate()
        else:
            if args.config:
                raise core.AppError('Service controls use the default configuration; omit --config.')
            result = core.service(args.setting if args.action == 'autostart' else args.action)
        if result is not None:
            if getattr(args, 'json', False):
                print(json.dumps(result, indent=2))
            elif args.action in ('start', 'stop', 'restart'):
                print({'start': 'Switching started.', 'stop': 'Switching stopped.',
                       'restart': 'Switching restarted.'}[args.action])
            elif args.action == 'autostart':
                print('Start at login ' + ('enabled.' if args.setting == 'enable' else 'disabled.'))
            elif args.action == 'status':
                service = result['service']
                print('Switching: ' + ('running' if service['active'] == 'active' else 'stopped'))
                print('Headset: ' + ('connected' if result.get('headset') == 'connected' else
                                    'unknown' if result.get('headset') == 'unknown' else 'disconnected'))
                print('Start at login: ' + ('enabled' if service['autostart'] else 'disabled'))
                output = result.get('daemon', {}).get('last_selected_output')
                if output:
                    print('Output: ' + output)
                errors = [service.get('error'), result.get('device_error'), result.get('configuration_error'),
                          result.get('daemon', {}).get('error')]
                for error in dict.fromkeys(e for e in errors if e):
                    print('Notice: ' + error)
            elif args.action == 'configure':
                print('Output devices saved. Run ps-pulse start to begin switching.')
            elif args.action == 'show-config':
                print('Headset: ' + result['headset_sink'])
                print('Fallback: ' + result['speakers_sink'])
            elif args.action == 'devices':
                for s in result:
                    print(f"{s['label']}{' [Pulse Elite]' if s['is_headset'] else ''}\n  {s['name']}")
            else:
                print(json.dumps(result, indent=2))
        return 0
    except (core.AppError, OSError) as exc:
        if getattr(args, 'json', False):
            print(json.dumps({'error': str(exc)}))
        else:
            print(f'Error: {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
