__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2021, Vanessa Sochat"
__license__ = "MIT"


def main(args, parser, extra, subparser):

    from oras.main import Client

    client = Client(quiet=args.quiet)
    print(client.version())
