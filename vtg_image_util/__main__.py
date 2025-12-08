"""
Entry point for Victor 9000 Disk Image Utility.

Allows running as: python -m vtg_image_util
"""

import argparse
import sys

from . import __version__
from .commands import cmd_attr, cmd_copy, cmd_create, cmd_delete, cmd_info, cmd_list, cmd_mkdir, cmd_rmdir, cmd_verify, print_extended_help
from .formatter import OutputFormatter
from .logging_config import setup_logging, QUIET, NORMAL, VERBOSE


def main() -> int:
    """Main entry point."""
    # Check for extended help before argparse
    if '--help-syntax' in sys.argv:
        print_extended_help()
        return 0

    parser = argparse.ArgumentParser(
        prog='vtg_image_util',
        description='Victor 9000 disk image utility (floppy and hard disk)',
        epilog='Use --help-syntax for detailed syntax and examples.'
    )

    # Global options
    parser.add_argument('--version', action='version',
                        version=f'%(prog)s {__version__}')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Show detailed output')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Suppress non-essential output')
    parser.add_argument('--json', action='store_true', help='Output in JSON format')
    parser.add_argument('--help-syntax', action='store_true',
                        help='Show detailed help with syntax and examples')

    subparsers = parser.add_subparsers(dest='command', required=True)

    # Verify command
    verify_parser = subparsers.add_parser('verify', help='Verify disk image integrity')
    verify_parser.add_argument('path', help='Disk image path to verify')
    verify_parser.add_argument('--json', action='store_true', help='Output in JSON format')

    # Create command
    create_parser = subparsers.add_parser('create', help='Create a new blank disk image')
    create_parser.add_argument('output', help='Output file path for new disk image')
    create_parser.add_argument('-t', '--type', required=True,
                               choices=['victor-ss', 'victor-ds', '360K', '720K', '1.2M', '1.44M'],
                               help='Disk type: victor-ss (single-sided), victor-ds (double-sided), '
                                    '360K, 720K, 1.2M, 1.44M (IBM PC)')
    create_parser.add_argument('-l', '--label', help='Volume label (optional)')
    create_parser.add_argument('-f', '--force', action='store_true',
                               help='Overwrite existing file')
    create_parser.add_argument('--json', action='store_true', help='Output in JSON format')

    # Info command
    info_parser = subparsers.add_parser('info', help='Show disk image information',
                                        epilog='Use -v for technical details.')
    info_parser.add_argument('path', help='Disk image path (image.img or image.img:N for partition)')
    info_parser.add_argument('--json', action='store_true', help='Output in JSON format')

    # List command
    list_parser = subparsers.add_parser('list', help='List files or partitions',
                                        epilog='Use --help-syntax for path syntax.')
    list_parser.add_argument('path', help='Disk image path (image.img or image.img:N:\\path)')
    list_parser.add_argument('-r', '--recursive', action='store_true',
                             help='List subdirectories recursively')
    list_parser.add_argument('--json', action='store_true', help='Output in JSON format')

    # Copy command
    copy_parser = subparsers.add_parser('copy', help='Copy files to/from disk image',
                                        epilog='Use --help-syntax for path syntax.')
    copy_parser.add_argument('source', help='Source path (supports wildcards: *.COM, *.*)')
    copy_parser.add_argument('dest', help='Destination path (use directory for wildcards)')
    copy_parser.add_argument('-r', '--recursive', action='store_true',
                             help='Copy subdirectories recursively')
    copy_parser.add_argument('--json', action='store_true', help='Output in JSON format')

    # Delete command
    delete_parser = subparsers.add_parser('delete', help='Delete file from disk image',
                                          epilog='Use --help-syntax for path syntax.')
    delete_parser.add_argument('path', help='File to delete (image.img:\\FILE or image.img:N:\\FILE)')
    delete_parser.add_argument('--json', action='store_true', help='Output in JSON format')

    # Attr command
    attr_parser = subparsers.add_parser('attr', help='View or modify file attributes',
                                        epilog='Attributes: R=readonly, H=hidden, S=system, A=archive. '
                                               'Use -- before -X flags (e.g., attr path -- +R -A)')
    attr_parser.add_argument('path', help='File path (image.img:\\FILE or image.img:N:\\FILE)')
    attr_parser.add_argument('modifications', nargs='*', metavar='MOD',
                             help='Attribute changes: +R +H +S +A to set, -R -H -S -A to clear')
    attr_parser.add_argument('--json', action='store_true', help='Output in JSON format')

    # Mkdir command
    mkdir_parser = subparsers.add_parser('mkdir', help='Create a directory on disk image')
    mkdir_parser.add_argument('path', help='Directory path (image.img:\\DIRNAME or image.img:N:\\DIRNAME)')
    mkdir_parser.add_argument('--json', action='store_true', help='Output in JSON format')

    # Rmdir command
    rmdir_parser = subparsers.add_parser('rmdir', help='Remove a directory from disk image')
    rmdir_parser.add_argument('path', help='Directory path (image.img:\\DIRNAME or image.img:N:\\DIRNAME)')
    rmdir_parser.add_argument('-r', '--recursive', action='store_true',
                              help='Remove directory and all contents recursively')
    rmdir_parser.add_argument('--json', action='store_true', help='Output in JSON format')

    args = parser.parse_args()

    # Configure logging based on verbosity flags
    if args.quiet:
        setup_logging(level=QUIET)
    elif args.verbose:
        setup_logging(level=VERBOSE)
    else:
        setup_logging(level=NORMAL)

    formatter = OutputFormatter(json_mode=args.json)

    match args.command:
        case 'verify':
            return cmd_verify(args, formatter)
        case 'create':
            return cmd_create(args, formatter)
        case 'info':
            return cmd_info(args, formatter)
        case 'list':
            return cmd_list(args, formatter)
        case 'copy':
            return cmd_copy(args, formatter)
        case 'delete':
            return cmd_delete(args, formatter)
        case 'attr':
            return cmd_attr(args, formatter)
        case 'mkdir':
            return cmd_mkdir(args, formatter)
        case 'rmdir':
            return cmd_rmdir(args, formatter)
        case _:
            formatter.error(f"Unknown command: {args.command}")
            return 1


if __name__ == '__main__':
    sys.exit(main())
