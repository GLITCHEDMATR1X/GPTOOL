import sys


def main():
    if any(arg in ('--panda-xr-proof', '--proof') for arg in sys.argv[1:]):
        from p3dopenxr.builder_core import main as builder_main
        builder_args = ['--proof' if arg == '--panda-xr-proof' else arg for arg in sys.argv[1:]]
        return builder_main(builder_args)

    from p3dopenxr.app import main as app_main
    app_main()
    return None


if __name__ == '__main__':
    raise SystemExit(main())
